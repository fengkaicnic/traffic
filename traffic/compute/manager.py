# vim: tabstop=4 shiftwidth=4 softtabstop=4
#coding=utf-8  

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Handles all processes relating to instances (guest vms).

The :py:class:`ComputeManager` class is a :py:class:`traffic.manager.Manager` that
handles RPC calls relating to creating instances.  It is responsible for
building a disk image, launching it via the underlying virtualization driver,
responding to calls to check its state, attaching persistent storage, and
terminating it.

**Related Flags**

:instances_path:  Where instances are kept on disk
:base_dir_name:  Where cached images are stored under instances_path
:compute_driver:  Name of class that is used to handle virtualization, loaded
                  by :func:`traffic.openstack.common.importutils.import_object`

"""

import contextlib
import functools
import socket
import sys
import time
import traceback

from eventlet import greenthread

from traffic import compute
from traffic.compute import rpcapi as compute_rpcapi
import traffic.context
from traffic import exception
from traffic import flags
from traffic import manager
from traffic.openstack.common import cfg
from traffic.openstack.common import excutils
from traffic.openstack.common import importutils
from traffic.openstack.common import jsonutils
from traffic.openstack.common import log as logging
from traffic.openstack.common.notifier import api as notifier
from traffic.openstack.common import rpc
from traffic.openstack.common.rpc import common as rpc_common
from traffic.openstack.common.rpc import dispatcher as rpc_dispatcher
from traffic.openstack.common import timeutils
from traffic import tqdisc
from traffic import tfilter
from traffic.scheduler import rpcapi as scheduler_rpcapi
from traffic import utils



compute_opts = [
    cfg.StrOpt('base_dir_name',
               default='_base',
               help="Where cached images are stored under $instances_path."
                    "This is NOT the full path - just a folder name."
                    "For per-compute-host cached images, set to _base_$my_ip"),
    cfg.StrOpt('console_host',
               default=socket.gethostname(),
               help='Console proxy host to use to connect '
                    'to instances on this host.'),
    cfg.IntOpt("rescue_timeout",
               default=0,
               help="Automatically unrescue an instance after N seconds. "
                    "Set to 0 to disable."),
    cfg.IntOpt('host_state_interval',
               default=120,
               help='Interval in seconds for querying the host status'),
    cfg.IntOpt("running_deleted_instance_timeout",
               default=0,
               help="Number of seconds after being deleted when a running "
                    "instance should be considered eligible for cleanup."),
    cfg.IntOpt("running_deleted_instance_poll_interval",
               default=30,
               help="Number of periodic scheduler ticks to wait between "
                    "runs of the cleanup task."),
    cfg.StrOpt("running_deleted_instance_action",
               default="noop",
               help="Action to take if a running deleted instance is detected."
                    "Valid options are 'noop', 'log' and 'reap'. "
                    "Set to 'noop' to disable."),
    cfg.IntOpt("image_cache_manager_interval",
               default=40,
               help="Number of periodic scheduler ticks to wait between "
                    "runs of the image cache manager."),
    cfg.IntOpt("heal_instance_info_cache_interval",
               default=60,
               help="Number of seconds between instance info_cache self "
                        "healing updates"),
    cfg.BoolOpt('instance_usage_audit',
               default=False,
               help="Generate periodic compute.instance.exists notifications"),
    ]

FLAGS = flags.FLAGS
FLAGS.register_opts(compute_opts)

LOG = logging.getLogger(__name__)


def publisher_id(host=None):
    return notifier.publisher_id("compute", host)


def reverts_task_state(function):
    """Decorator to revert task_state on failure"""

    @functools.wraps(function)
    def decorated_function(self, context, *args, **kwargs):
        try:
            return function(self, context, *args, **kwargs)
        except exception.UnexpectedTaskStateError:
            LOG.exception(_("Possibly task preempted."))
            # Note(maoy): unexpected task state means the current
            # task is preempted. Do not clear task state in this
            # case.
            raise
        except Exception:
            with excutils.save_and_reraise_exception():
                try:
                    self._instance_update(context,
                                          kwargs['instance']['uuid'],
                                          task_state=None)
                except Exception:
                    pass

    return decorated_function

class ComputeManager(manager.SchedulerDependentManager):
    """Manages the running instances from creation to destruction."""

    RPC_API_VERSION = '2.2'

    def __init__(self, compute_driver=None, *args, **kwargs):
        """Load configuration options and connect to the hypervisor."""
        # TODO(vish): sync driver creation logic with the rest of the system
        #             and re-document the module docstring

        super(ComputeManager, self).__init__(service_name="traffic",
                                             *args, **kwargs)
        #wyk:a compute service can manage multiple compute nodes(distin by nodename)
        #for each compute node, exists a resource_tracker
        self._resource_tracker_dict = {}
        self.tqdisc_api = tqdisc.API()
        self.tfilter_api = tfilter.API()

    def get_console_topic(self, context):
        """Retrieves the console host for a project on this host.

        Currently this is just set in the flags for each compute host.

        """
        #TODO(mdragon): perhaps make this variable by console_type?
        return rpc.queue_get_for(context,
                                 FLAGS.console_topic,
                                 FLAGS.console_host)


    def _get_instance_nw_info(self, context, instance):
        """Get a list of dictionaries of network data of an instance."""
        # get the network info from network
        network_info = self.network_api.get_instance_nw_info(context,
                                                             instance)
        return network_info

    def _legacy_nw_info(self, network_info):
        """Converts the model nw_info object to legacy style"""
        if self.driver.legacy_nwinfo():
            network_info = network_info.legacy()
        return network_info

    def _run_instance(self, context, request_spec,
                      filter_properties, requested_networks, injected_files,
                      admin_password, is_first_time, instance):
        """Launch a new instance with specified options."""
        context = context.elevated()

        try:
            self._check_instance_not_already_created(context, instance)
            image_meta = self._check_image_size(context, instance)
            extra_usage_info = {"image_name": image_meta['name']}
            self._start_building(context, instance)
            self._notify_about_instance_usage(
                    context, instance, "create.start",
                    extra_usage_info=extra_usage_info)
            network_info = self._allocate_network(context, instance, requested_networks)
            rt = self._get_resource_tracker(instance.get('node'))
            try:
                limits = filter_properties.get('limits', {})
                with rt.resource_claim(context, instance, limits):
                    # Resources are available to build this instance here,
                    # mark it as belonging to this host:
                    self._instance_update(context, instance['uuid'],
                            host=self.host, launched_on=self.host)

                    block_device_info = self._prep_block_device(context,
                            instance)
                    instance = self._spawn(context, instance, image_meta,
                                           network_info, block_device_info,
                                           injected_files, admin_password)

            except exception.InstanceNotFound:
                raise  # the instance got deleted during the spawn
            except Exception:
                # try to re-schedule instance:
                self._reschedule_or_reraise(context, instance,
                        requested_networks, admin_password, injected_files,
                        is_first_time, request_spec, filter_properties)
            else:
                # Spawn success:
                if (is_first_time and not instance['access_ip_v4']
                                  and not instance['access_ip_v6']):
                    self._update_access_ip(context, instance, network_info)

                self._notify_about_instance_usage(context, instance,
                        "create.end", network_info=network_info,
                        extra_usage_info=extra_usage_info)
        except Exception:
            with excutils.save_and_reraise_exception():
                self._set_instance_error_state(context, instance['uuid'])

    def _reschedule_or_reraise(self, context, instance, requested_networks,
                               admin_password, injected_files, is_first_time,
                               request_spec, filter_properties):
        """Try to re-schedule the build or re-raise the original build error to
        error out the instance.
        """
        type_, value, tb = sys.exc_info()  # save original exception
        rescheduled = False
        instance_uuid = instance['uuid']

        def _log_original_error():
            LOG.error(_('Build error: %s') %
                    traceback.format_exception(type_, value, tb),
                    instance_uuid=instance_uuid)

        try:
            self._deallocate_network(context, instance)
        except Exception:
            # do not attempt retry if network de-allocation occurs:
            _log_original_error()
            raise

        try:
            rescheduled = self._reschedule(context, instance_uuid,
                    requested_networks, admin_password, injected_files,
                    is_first_time, request_spec, filter_properties)
        except Exception:
            rescheduled = False
            LOG.exception(_("Error trying to reschedule"),
                          instance_uuid=instance_uuid)

        if rescheduled:
            # log the original build error
            _log_original_error()
        else:
            # not re-scheduling
            raise type_, value, tb



    def create_traffic(self, context, ip, instanceid, band, prio):
        classid = self.tqdisc_api.create(context, instanceid, band, prio)
        self.tfilter_api.create(context, ip, classid, prio)


    def _deallocate_network(self, context, instance):
        LOG.debug(_('Deallocating network for instance'), instance=instance)
        self.network_api.deallocate_for_instance(context, instance)


    def _get_instance_volume_block_device_info(self, context, instance_uuid):
        bdms = self._get_instance_volume_bdms(context, instance_uuid)
        block_device_mapping = []
        for bdm in bdms:
            try:
                cinfo = jsonutils.loads(bdm['connection_info'])
                if cinfo and 'serial' not in cinfo:
                    cinfo['serial'] = bdm['volume_id']
                bdmap = {'connection_info': cinfo,
                         'mount_device': bdm['device_name'],
                         'delete_on_termination': bdm['delete_on_termination']}
                block_device_mapping.append(bdmap)
            except TypeError:
                # if the block_device_mapping has no value in connection_info
                # (returned as None), don't include in the mapping
                pass
        # NOTE(vish): The mapping is passed in so the driver can disconnect
        #             from remote volumes if necessary
        return {'block_device_mapping': block_device_mapping}


    def run_instance(self, context, instance, request_spec=None,
                     filter_properties=None, requested_networks=None,
                     injected_files=None, admin_password=None,
                     is_first_time=False):

        if filter_properties is None:
            filter_properties = {}
        if injected_files is None:
            injected_files = []

        @utils.synchronized(instance['uuid'])
        def do_run_instance():
            self._run_instance(context, request_spec,
                    filter_properties, requested_networks, injected_files,
                    admin_password, is_first_time, instance)
        do_run_instance()

    def _cleanup_volumes(self, context, instance_uuid):
        bdms = self.db.block_device_mapping_get_all_by_instance(context,
                                                                instance_uuid)
        for bdm in bdms:
            LOG.debug(_("terminating bdm %s") % bdm,
                      instance_uuid=instance_uuid)
            if bdm['volume_id'] and bdm['delete_on_termination']:
                volume = self.volume_api.get(context, bdm['volume_id'])
                self.volume_api.delete(context, volume)
            # NOTE(vish): bdms will be deleted on instance destroy



    def terminate_instance(self, context, instance):
        """Terminate an instance on this host.  """
        # Note(eglynn): we do not decorate this action with reverts_task_state
        # because a failure during termination should leave the task state as
        # DELETING, as a signal to the API layer that a subsequent deletion
        # attempt should not result in a further decrement of the quota_usages
        # in_use count (see bug 1046236).

        elevated = context.elevated()

        @utils.synchronized(instance['uuid'])
        def do_terminate_instance(instance):
            try:
                self._delete_instance(context, instance)
            except exception.InstanceTerminationFailure as error:
                msg = _('%s. Setting instance vm_state to ERROR')
                LOG.error(msg % error, instance=instance)
                self._set_instance_error_state(context, instance['uuid'])
            except exception.InstanceNotFound as e:
                LOG.warn(e, instance=instance)

        do_terminate_instance(instance)

    def start_instance(self, context, instance):
        """Starting an instance on this host.

        Alias for power_on_instance for compatibility"""
        self.power_on_instance(context, instance)

    def confirm_resize(self, context, migration_id, instance,
                       reservations=None):
        """Destroys the source instance."""
        migration_ref = self.db.migration_get(context, migration_id)

        self._notify_about_instance_usage(context, instance,
                                          "resize.confirm.start")

        with self._error_out_instance_on_exception(context, instance['uuid'],
                                                   reservations):
            # NOTE(tr3buchet): tear down networks on source host
            self.network_api.setup_networks_on_host(context, instance,
                               migration_ref['source_compute'], teardown=True)

            network_info = self._get_instance_nw_info(context, instance)
            self.driver.confirm_migration(migration_ref, instance,
                                          self._legacy_nw_info(network_info))

            self._notify_about_instance_usage(
                context, instance, "resize.confirm.end",
                network_info=network_info)

            self._quota_commit(context, reservations)

    def reset_network(self, context, instance):
        """Reset networking on the given instance."""
        LOG.debug(_('Reset network'), context=context, instance=instance)
        self.driver.reset_network(instance)

    def _inject_network_info(self, context, instance):
        """Inject network info for the given instance."""
        LOG.debug(_('Inject network info'), context=context, instance=instance)

        network_info = self._get_instance_nw_info(context, instance)
        LOG.debug(_('network_info to inject: |%s|'), network_info,
                  instance=instance)

        self.driver.inject_network_info(instance,
                                        self._legacy_nw_info(network_info))
        return network_info

    def inject_network_info(self, context, instance):
        """Inject network info, but don't return the info."""
        self._inject_network_info(context, instance)

    def get_console_output(self, context, instance, tail_length=None):
        """Send the console output for the given instance."""
        context = context.elevated()
        LOG.audit(_("Get console output"), context=context,
                  instance=instance)
        output = self.driver.get_console_output(instance)

        if tail_length is not None:
            output = self._tail_log(output, tail_length)

        return output.decode('utf-8', 'replace').encode('ascii', 'replace')

    def _tail_log(self, log, length):
        try:
            length = int(length)
        except ValueError:
            length = 0

        if length == 0:
            return ''
        else:
            return '\n'.join(log.split('\n')[-int(length):])

    def get_vnc_console(self, context, console_type, instance):
        """Return connection information for a vnc console."""
        context = context.elevated()
        LOG.debug(_("Getting vnc console"), instance=instance)
        token = str(utils.gen_uuid())

        if console_type == 'novnc':
            # For essex, novncproxy_base_url must include the full path
            # including the html file (like http://myhost/vnc_auto.html)
            access_url = '%s?token=%s' % (FLAGS.novncproxy_base_url, token)
        elif console_type == 'xvpvnc':
            access_url = '%s?token=%s' % (FLAGS.xvpvncproxy_base_url, token)
        else:
            raise exception.ConsoleTypeInvalid(console_type=console_type)

        # Retrieve connect info from driver, and then decorate with our
        # access info token
        connect_info = self.driver.get_vnc_console(instance)
        connect_info['token'] = token
        connect_info['access_url'] = access_url

        return connect_info

    def _attach_volume_boot(self, context, instance, volume, mountpoint):
        """Attach a volume to an instance at boot time. So actual attach
        is done by instance creation"""

        instance_id = instance['id']
        instance_uuid = instance['uuid']
        volume_id = volume['id']
        context = context.elevated()
        LOG.audit(_('Booting with volume %(volume_id)s at %(mountpoint)s'),
                  locals(), context=context, instance=instance)
        connector = self.driver.get_volume_connector(instance)
        connection_info = self.volume_api.initialize_connection(context,
                                                                volume,
                                                                connector)
        self.volume_api.attach(context, volume, instance_uuid, mountpoint)
        return connection_info

    
    
    # Added by YANGYUAN         
    def attach_image(self, context, image_id, mountpoint, instance):
        """Attach a image to an instance."""
        try:
            return self._attach_image(context, image_id,
                                       mountpoint, instance)
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.update_instance_cdrom_active(
                        context, instance['uuid'], False)
                

    #Added by YANGYUAN
    def detach_image(self, context, instance, mountpoint=None):
        """Detach a volume from an instance."""
        try:
            if (mountpoint == None or mountpoint == ""):
                mountpoint = "/deb/hdb"
            self.driver.detach_image( instance['name'],
                                          mountpoint)
            self.db.update_instance_cdrom_active(
                        context, instance['uuid'], False)
        except:
            self.db.update_instance_cdrom_active(
                        context, instance['uuid'], True)
        return True
 
    def attach_volume(self, context, volume_id, mountpoint, instance):
        """Attach a volume to an instance."""
        try:
            return self._attach_volume(context, volume_id,
                                       mountpoint, instance)
        except Exception:
            with excutils.save_and_reraise_exception():
                self.db.block_device_mapping_destroy_by_instance_and_device(
                        context, instance.get('uuid'), mountpoint)

    def _attach_volume(self, context, volume_id, mountpoint, instance):
        volume = self.volume_api.get(context, volume_id)
        context = context.elevated()
        LOG.audit(_('Attaching volume %(volume_id)s to %(mountpoint)s'),
                  locals(), context=context, instance=instance)
        try:
            connector = self.driver.get_volume_connector(instance)
            connection_info = self.volume_api.initialize_connection(context,
                                                                    volume,
                                                                    connector)
        except Exception:  # pylint: disable=W0702
            with excutils.save_and_reraise_exception():
                msg = _("Failed to connect to volume %(volume_id)s "
                        "while attaching at %(mountpoint)s")
                LOG.exception(msg % locals(), context=context,
                              instance=instance)
                self.volume_api.unreserve_volume(context, volume)

        if 'serial' not in connection_info:
            connection_info['serial'] = volume_id

        try:
            self.driver.attach_volume(connection_info,
                                      instance['name'],
                                      mountpoint)
        except Exception:  # pylint: disable=W0702
            with excutils.save_and_reraise_exception():
                msg = _("Failed to attach volume %(volume_id)s "
                        "at %(mountpoint)s")
                LOG.exception(msg % locals(), context=context,
                              instance=instance)
                self.volume_api.terminate_connection(context,
                                                     volume,
                                                     connector)

        self.volume_api.attach(context,
                               volume,
                               instance['uuid'],
                               mountpoint)
        values = {
            'instance_uuid': instance['uuid'],
            'connection_info': jsonutils.dumps(connection_info),
            'device_name': mountpoint,
            'delete_on_termination': False,
            'virtual_name': None,
            'snapshot_id': None,
            'volume_id': volume_id,
            'volume_size': None,
            'no_device': None}
        self.db.block_device_mapping_update_or_create(context, values)

    def _detach_volume(self, context, instance, bdm):
        """Do the actual driver detach using block device mapping."""
        mp = bdm['device_name']
        volume_id = bdm['volume_id']

        LOG.audit(_('Detach volume %(volume_id)s from mountpoint %(mp)s'),
                  locals(), context=context, instance=instance)

        if instance['name'] not in self.driver.list_instances():
            LOG.warn(_('Detaching volume from unknown instance'),
                     context=context, instance=instance)
        connection_info = jsonutils.loads(bdm['connection_info'])
        # NOTE(vish): We currently don't use the serial when disconnecting,
        #             but added for completeness in case we ever do.
        if connection_info and 'serial' not in connection_info:
            connection_info['serial'] = volume_id
        try:
            self.driver.detach_volume(connection_info,
                                      instance['name'],
                                      mp)
        except Exception:  # pylint: disable=W0702
            with excutils.save_and_reraise_exception():
                msg = _("Faild to detach volume %(volume_id)s from %(mp)s")
                LOG.exception(msg % locals(), context=context,
                              instance=instance)
                volume = self.volume_api.get(context, volume_id)
                self.volume_api.roll_detaching(context, volume)

    def detach_volume(self, context, volume_id, instance):
        """Detach a volume from an instance."""
        bdm = self._get_instance_volume_bdm(context, instance['uuid'],
                                            volume_id)
        self._detach_volume(context, instance, bdm)
        volume = self.volume_api.get(context, volume_id)
        connector = self.driver.get_volume_connector(instance)
        self.volume_api.terminate_connection(context, volume, connector)
        self.volume_api.detach(context.elevated(), volume)
        self.db.block_device_mapping_destroy_by_instance_and_volume(
            context, instance['uuid'], volume_id)

    def remove_volume_connection(self, context, volume_id, instance):
        """Remove a volume connection using the volume api"""
        # NOTE(vish): We don't want to actually mark the volume
        #             detached, or delete the bdm, just remove the
        #             connection from this host.
        try:
            bdm = self._get_instance_volume_bdm(context,
                                                instance['uuid'],
                                                volume_id)
            self._detach_volume(context, instance, bdm)
            volume = self.volume_api.get(context, volume_id)
            connector = self.driver.get_volume_connector(instance)
            self.volume_api.terminate_connection(context, volume, connector)
        except exception.NotFound:
            pass

    def check_can_live_migrate_destination(self, ctxt, instance,
                                           block_migration=False,
                                           disk_over_commit=False):
        """Check if it is possible to execute live migration.

        This runs checks on the destination host, and then calls
        back to the source host to check the results.

        :param context: security context
        :param instance: dict of instance data
        :param block_migration: if true, prepare for block migration
        :param disk_over_commit: if true, allow disk over commit

        Returns a mapping of values required in case of block migration
        and None otherwise.
        """
        dest_check_data = self.driver.check_can_live_migrate_destination(ctxt,
            instance, block_migration, disk_over_commit)
        try:
            self.compute_rpcapi.check_can_live_migrate_source(ctxt,
                    instance, dest_check_data)
        finally:
            self.driver.check_can_live_migrate_destination_cleanup(ctxt,
                    dest_check_data)
        if dest_check_data and 'migrate_data' in dest_check_data:
            return dest_check_data['migrate_data']

    def check_can_live_migrate_source(self, ctxt, instance, dest_check_data):
        """Check if it is possible to execute live migration.

        This checks if the live migration can succeed, based on the
        results from check_can_live_migrate_destination.

        :param context: security context
        :param instance: dict of instance data
        :param dest_check_data: result of check_can_live_migrate_destination
        """
        self.driver.check_can_live_migrate_source(ctxt, instance,
                                                  dest_check_data)

    def pre_live_migration(self, context, instance,
                           block_migration=False, disk=None):
        """Preparations for live migration at dest host.

        :param context: security context
        :param instance: dict of instance data
        :param block_migration: if true, prepare for block migration

        """
        # If any volume is mounted, prepare here.
        block_device_info = self._get_instance_volume_block_device_info(
                            context, instance['uuid'])
        if not block_device_info['block_device_mapping']:
            LOG.info(_('Instance has no volume.'), instance=instance)

        network_info = self._get_instance_nw_info(context, instance)

        # TODO(tr3buchet): figure out how on the earth this is necessary
        fixed_ips = network_info.fixed_ips()
        if not fixed_ips:
            raise exception.FixedIpNotFoundForInstance(
                                       instance_uuid=instance['uuid'])

        self.driver.pre_live_migration(context, instance,
                                       block_device_info,
                                       self._legacy_nw_info(network_info))

        # NOTE(tr3buchet): setup networks on destination host
        self.network_api.setup_networks_on_host(context, instance,
                                                         self.host)

        # Creating filters to hypervisors and firewalls.
        # An example is that traffic-instance-instance-xxx,
        # which is written to libvirt.xml(Check "virsh nwfilter-list")
        # This nwfilter is necessary on the destination host.
        # In addition, this method is creating filtering rule
        # onto destination host.
        self.driver.ensure_filtering_rules_for_instance(instance,
                                            self._legacy_nw_info(network_info))

        # Preparation for block migration
        if block_migration:
            self.driver.pre_block_migration(context, instance, disk)

    def live_migration(self, context, dest, instance,
                       block_migration=False, migrate_data=None):
        """Executing live migration.

        :param context: security context
        :param instance: instance dict
        :param dest: destination host
        :param block_migration: if true, prepare for block migration
        :param migrate_data: implementation specific params

        """
        try:
            if block_migration:
                disk = self.driver.get_instance_disk_info(instance['name'])
            else:
                disk = None

            self.compute_rpcapi.pre_live_migration(context, instance,
                    block_migration, disk, dest)

        except Exception:
            with excutils.save_and_reraise_exception():
                LOG.exception(_('Pre live migration failed at  %(dest)s'),
                              locals(), instance=instance)
                self._rollback_live_migration(context, instance, dest,
                                              block_migration)

        # Executing live migration
        # live_migration might raises exceptions, but
        # nothing must be recovered in this version.
        self.driver.live_migration(context, instance, dest,
                                   self._post_live_migration,
                                   self._rollback_live_migration,
                                   block_migration, migrate_data)

    def _post_live_migration(self, ctxt, instance_ref,
                            dest, block_migration=False):
        """Post operations for live migration.

        This method is called from live_migration
        and mainly updating database record.

        :param ctxt: security context
        :param instance_ref: traffic.db.sqlalchemy.models.Instance
        :param dest: destination host
        :param block_migration: if true, prepare for block migration

        """
        LOG.info(_('_post_live_migration() is started..'),
                 instance=instance_ref)

        # Detaching volumes.
        for bdm in self._get_instance_volume_bdms(ctxt, instance_ref['uuid']):
            # NOTE(vish): We don't want to actually mark the volume
            #             detached, or delete the bdm, just remove the
            #             connection from this host.
            self.remove_volume_connection(ctxt, bdm['volume_id'],
                                          instance_ref)

        # Releasing vlan.
        # (not necessary in current implementation?)

        network_info = self._get_instance_nw_info(ctxt, instance_ref)
        # Releasing security group ingress rule.
        self.driver.unfilter_instance(instance_ref,
                                      self._legacy_nw_info(network_info))

        # Database updating.
        # NOTE(jkoelker) This needs to be converted to network api calls
        #                if traffic wants to support floating_ips in
        #                quantum/melange
        try:
            # Not return if floating_ip is not found, otherwise,
            # instance never be accessible..
            floating_ip = self.db.instance_get_floating_address(ctxt,
                                                         instance_ref['id'])
            if not floating_ip:
                LOG.info(_('No floating_ip found'), instance=instance_ref)
            else:
                floating_ip_ref = self.db.floating_ip_get_by_address(ctxt,
                                                              floating_ip)
                self.db.floating_ip_update(ctxt,
                                           floating_ip_ref['address'],
                                           {'host': dest})
        except exception.NotFound:
            LOG.info(_('No floating_ip found.'), instance=instance_ref)
        except Exception, e:
            LOG.error(_('Live migration: Unexpected error: cannot inherit '
                        'floating ip.\n%(e)s'), locals(),
                      instance=instance_ref)

        # Define domain at destination host, without doing it,
        # pause/suspend/terminate do not work.
        self.compute_rpcapi.post_live_migration_at_destination(ctxt,
                instance_ref, block_migration, dest)

        # No instance booting at source host, but instance dir
        # must be deleted for preparing next block migration
        if block_migration:
            self.driver.destroy(instance_ref,
                                self._legacy_nw_info(network_info))
        else:
            # self.driver.destroy() usually performs  vif unplugging
            # but we must do it explicitly here when block_migration
            # is false, as the network devices at the source must be
            # torn down
            self.driver.unplug_vifs(instance_ref,
                                    self._legacy_nw_info(network_info))

        # NOTE(tr3buchet): tear down networks on source host
        self.network_api.setup_networks_on_host(ctxt, instance_ref,
                                                self.host, teardown=True)

        LOG.info(_('Migrating instance to %(dest)s finished successfully.'),
                 locals(), instance=instance_ref)
        LOG.info(_("You may see the error \"libvirt: QEMU error: "
                   "Domain not found: no domain with matching name.\" "
                   "This error can be safely ignored."),
                 instance=instance_ref)

 


    def rollback_live_migration_at_destination(self, context, instance):
        """ Cleaning up image directory that is created pre_live_migration.

        :param context: security context
        :param instance: an Instance dict sent over rpc
        """
        network_info = self._get_instance_nw_info(context, instance)

        # NOTE(tr3buchet): tear down networks on destination host
        self.network_api.setup_networks_on_host(context, instance,
                                                self.host, teardown=True)

        # NOTE(vish): The mapping is passed in so the driver can disconnect
        #             from remote volumes if necessary
        block_device_info = self._get_instance_volume_block_device_info(
                            context, instance['uuid'])
        self.driver.destroy(instance, self._legacy_nw_info(network_info),
                            block_device_info)

    def _report_driver_status(self, context):
        curr_time = time.time()
        if curr_time - self._last_host_check > FLAGS.host_state_interval:
            self._last_host_check = curr_time
            LOG.info(_("Updating host status"))
            # This will grab info about the host and queue it
            # to be sent to the Schedulers.
            capabilities = self.driver.get_host_stats(refresh=True)
            for capability in (capabilities if isinstance(capabilities, list) else [capabilities]):
                capability['host_ip'] = FLAGS.my_ip
            self.update_service_capabilities(capabilities)


    def update_available_resource(self, context):
        """See driver.get_available_resource()

        Periodic process that keeps that the compute host's understanding of
        resource availability and usage in sync with the underlying hypervisor.

        :param context: security context
        """
        new_resource_tracker_dict = {}
        nodenames = self.driver.get_available_nodes()
        for nodename in nodenames:
            rt = self._get_resource_tracker(nodename)
            rt.update_available_resource(context)
            new_resource_tracker_dict[nodename] = rt
        self._resource_tracker_dict = new_resource_tracker_dict 

    def _cleanup_running_deleted_instances(self, context):
        """Cleanup any instances which are erroneously still running after
        having been deleted.

        Valid actions to take are:

            1. noop - do nothing
            2. log - log which instances are erroneously running
            3. reap - shutdown and cleanup any erroneously running instances

        The use-case for this cleanup task is: for various reasons, it may be
        possible for the database to show an instance as deleted but for that
        instance to still be running on a host machine (see bug
        https://bugs.launchpad.net/traffic/+bug/911366).

        This cleanup task is a cross-hypervisor utility for finding these
        zombied instances and either logging the discrepancy (likely what you
        should do in production), or automatically reaping the instances (more
        appropriate for dev environments).
        """
        action = FLAGS.running_deleted_instance_action

        if action == "noop":
            return

        # NOTE(sirp): admin contexts don't ordinarily return deleted records
        with utils.temporary_mutation(context, read_deleted="yes"):
            for instance in self._running_deleted_instances(context):
                if action == "log":
                    name = instance['name']
                    LOG.warning(_("Detected instance with name label "
                                  "'%(name)s' which is marked as "
                                  "DELETED but still present on host."),
                                locals(), instance=instance)

                elif action == 'reap':
                    name = instance['name']
                    LOG.info(_("Destroying instance with name label "
                               "'%(name)s' which is marked as "
                               "DELETED but still present on host."),
                             locals(), instance=instance)
                    self._shutdown_instance(context, instance)
                    self._cleanup_volumes(context, instance['uuid'])
                else:
                    raise Exception(_("Unrecognized value '%(action)s'"
                                      " for FLAGS.running_deleted_"
                                      "instance_action"), locals(),
                                    instance=instance)

    def _running_deleted_instances(self, context):
        """Returns a list of instances traffic thinks is deleted,
        but the hypervisor thinks is still running. This method
        should be pushed down to the virt layer for efficiency.
        """
        def deleted_instance(instance):
            timeout = FLAGS.running_deleted_instance_timeout
            present = instance.name in present_name_labels
            erroneously_running = instance.deleted and present
            old_enough = (not instance.deleted_at or
                          timeutils.is_older_than(instance.deleted_at,
                                                  timeout))
            if erroneously_running and old_enough:
                return True
            return False
        present_name_labels = set(self.driver.list_instances())
        instances = self.db.instance_get_all_by_host(context, self.host)
        return [i for i in instances if deleted_instance(i)]

    @contextlib.contextmanager
    def _error_out_instance_on_exception(self, context, instance_uuid,
                                        reservations=None):
        try:
            yield
        except Exception, error:
            self._quota_rollback(context, reservations)
            with excutils.save_and_reraise_exception():
                msg = _('%s. Setting instance vm_state to ERROR')
                LOG.error(msg % error, instance_uuid=instance_uuid)
                self._set_instance_error_state(context, instance_uuid)

    def add_aggregate_host(self, context, aggregate_id, host, slave_info=None):
        """Notify hypervisor of change (for hypervisor pools)."""
        aggregate = self.db.aggregate_get(context, aggregate_id)
        try:
            self.driver.add_to_aggregate(context, aggregate, host,
                                         slave_info=slave_info)
        except exception.AggregateError:
            with excutils.save_and_reraise_exception():
                self.driver.undo_aggregate_operation(context,
                                               self.db.aggregate_host_delete,
                                               aggregate.id, host)

    def remove_aggregate_host(self, context, aggregate_id,
                              host, slave_info=None):
        """Removes a host from a physical hypervisor pool."""
        aggregate = self.db.aggregate_get(context, aggregate_id)
        try:
            self.driver.remove_from_aggregate(context, aggregate, host,
                                              slave_info=slave_info)
        except (exception.AggregateError,
                exception.InvalidAggregateAction) as e:
            with excutils.save_and_reraise_exception():
                self.driver.undo_aggregate_operation(
                                    context, self.db.aggregate_host_add,
                                    aggregate.id, host,
                                    isinstance(e, exception.AggregateError))

    #TODO:fix this bug
    #this task will remove some base image in use
#        ticks_between_runs=FLAGS.image_cache_manager_interval)
    def _run_image_cache_manager_pass(self, context):
        """Run a single pass of the image cache manager."""

        if FLAGS.image_cache_manager_interval == 0:
            return

        try:
            self.driver.manage_image_cache(context)
        except NotImplementedError:
            pass

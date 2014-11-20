# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2010 OpenStack, LLC.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
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

"""
Scheduler Service
"""

import functools
import sys

from traffic.compute import utils as compute_utils
from traffic import db
from traffic import exception
from traffic import flags
from traffic import manager
from traffic.openstack.common import cfg
from traffic.openstack.common import excutils
from traffic.openstack.common import importutils
from traffic.openstack.common import log as logging
from traffic.openstack.common.notifier import api as notifier
from traffic.openstack.common.rpc import common as rpc_common
from traffic.openstack.common import rpc
from traffic.compute import rpcapi as compute_rpcapi


LOG = logging.getLogger(__name__)

scheduler_driver_opt = cfg.StrOpt('scheduler_driver',
        default='traffic.scheduler.multi.MultiScheduler',
        help='Default driver to use for the scheduler')

FLAGS = flags.FLAGS
FLAGS.register_opt(scheduler_driver_opt)


def _compute_topic(topic, ctxt, host, instance):
    '''Get the topic to use for a message.

    :param topic: the base topic
    :param ctxt: request context
    :param host: explicit host to send the message to.
    :param instance: If an explicit host was not specified, use
                     instance['host']

    :returns: A topic string
    '''
    if not host:
        if not instance:
            raise exception.TrafficException(_('No compute host specified'))
        host = instance['host']
    if not host:
        raise exception.TrafficException(_('Unable to find host for '
                                           'Instance %s') % instance['uuid'])
    return rpc.queue_get_for(ctxt, topic, host)

class SchedulerManager(manager.Manager):
    """Chooses a host to run instances on."""

    RPC_API_VERSION = '2.2'

    def __init__(self, scheduler_driver=None, *args, **kwargs):
        '''if not scheduler_driver:
            scheduler_driver = FLAGS.scheduler_driver
        self.driver = importutils.import_object(scheduler_driver)'''
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        super(SchedulerManager, self).__init__(*args, **kwargs)

    def update_service_capabilities(self, context, service_name,
                                    host, capabilities):
        """Process a capability update from a service node."""
        if capabilities is None:
            capabilities = {}
        self.driver.update_service_capabilities(service_name, host,
                capabilities)

    def create_volume(self, context, volume_id, snapshot_id,
                      reservations=None, image_id=None):
        try:
            self.driver.schedule_create_volume(
                context, volume_id, snapshot_id, image_id)
        except Exception as ex:
            with excutils.save_and_reraise_exception():
                LOG.warning(_("Failed to schedule create_volume: %(ex)s") %
                            locals())
                db.volume_update(context, volume_id, {'status': 'error'})
                
    def create_traffic(self, context, ip, instance_id, band, host, mac, prio=1):
        
        self.compute_rpcapi.create_traffic(context, ip=ip,
                instance_id=instance_id,
                band=band, mac=mac, prio=prio, host=host)

    # NOTE (masumotok) : This method should be moved to traffic.api.ec2.admin.
    # Based on bexar design summit discussion,
    # just put this here for bexar release.
    def show_host_resources(self, context, host):
        """Shows the physical/usage resource given by hosts.

        :param context: security context
        :param host: hostname
        :returns:
            example format is below::

                {'resource':D, 'usage':{proj_id1:D, proj_id2:D}}
                D: {'vcpus': 3, 'memory_mb': 2048, 'local_gb': 2048,
                    'vcpus_used': 12, 'memory_mb_used': 10240,
                    'local_gb_used': 64}

        """
        # Getting compute node info and related instances info
        compute_ref = db.service_get_all_compute_by_host(context, host)
        compute_ref = compute_ref[0]
        instance_refs = db.instance_get_all_by_host(context,
                                                    compute_ref['host'])

        # Getting total available/used resource
        compute_ref = compute_ref['compute_node'][0]
        resource = {'vcpus': compute_ref['vcpus'],
                    'memory_mb': compute_ref['memory_mb'],
                    'local_gb': compute_ref['local_gb'],
                    'vcpus_used': compute_ref['vcpus_used'],
                    'memory_mb_used': compute_ref['memory_mb_used'],
                    'local_gb_used': compute_ref['local_gb_used']}
        usage = dict()
        if not instance_refs:
            return {'resource': resource, 'usage': usage}

        # Getting usage resource per project
        project_ids = [i['project_id'] for i in instance_refs]
        project_ids = list(set(project_ids))
        for project_id in project_ids:
            vcpus = [i['vcpus'] for i in instance_refs
                     if i['project_id'] == project_id]

            mem = [i['memory_mb'] for i in instance_refs
                   if i['project_id'] == project_id]

            root = [i['root_gb'] for i in instance_refs
                    if i['project_id'] == project_id]

            ephemeral = [i['ephemeral_gb'] for i in instance_refs
                         if i['project_id'] == project_id]

            usage[project_id] = {'vcpus': sum(vcpus),
                                 'memory_mb': sum(mem),
                                 'root_gb': sum(root),
                                 'ephemeral_gb': sum(ephemeral)}

        return {'resource': resource, 'usage': usage}


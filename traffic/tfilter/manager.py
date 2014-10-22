
from traffic import context
from traffic import exception
from traffic import flags
from traffic import manager
from traffic.openstack.common import cfg
from traffic.openstack.common import excutils
from traffic.openstack.common import importutils
from traffic.openstack.common import log as logging
from traffic.openstack.common import timeutils
from traffic import utils

LOG = logging.getLogger(__name__)

traffic_manager_opts = [
    cfg.StrOpt('storage_availability_zone',
               default='nova',
               help='availability zone of this service'),
    cfg.StrOpt('volume_driver',
               default='nova.volume.driver.ISCSIDriver',
               help='Driver to use for volume creation'),
    cfg.BoolOpt('use_local_volumes',
                default=True,
                help='if True, will not discover local volumes'),
    cfg.BoolOpt('volume_force_update_capabilities', 
                default=False,
                help='if True will force update capabilities on each check'),
    ]

FLAGS = flags.FLAGS
FLAGS.register_opts(traffic_manager_opts)

class TFilterManager(manager.Manager):
    
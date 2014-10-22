
import traffic.flags
import traffic.openstack.common.importutils

API = traffic.openstack.common.importutils.import_class(
              traffic.flags.FLAGS.compute_api_class)

import traffic.flags
import traffic.openstack.common.importutils

API = traffic.openstack.common.importutils.import_class(
              traffic.flags.FLAGS.traffic_api_class)
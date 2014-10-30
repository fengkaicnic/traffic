
import traffic.flags
import traffic.openstack.common.importutils

def API():
    importutils = traffic.openstack.common.importutils
    cls = importutils.import_class(traffic.flags.FLAGS.tfilter_api_class)
    return cls()
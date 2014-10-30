
import traffic.flags
import traffic.openstack.common.importutils

def API():
    importutils = traffic.openstack.common.importutils
    cls = importutils.import_class(traffic.flags.FLAGS.tqdisc_api_class)
    return cls()
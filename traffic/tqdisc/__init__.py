
import traffic.flags
import traffic.openstack.common.importutils

def API():
    importutils = traffic.openstack.common.importutils
    cls = importutils.import_class(traffic.flags.FLAGS.tqdisc_class_api)
    return cls()
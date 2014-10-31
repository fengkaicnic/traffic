
from traffic import flags
from traffic import utils
from traffic import rootwrap
from traffic.db import base

class API(base.Base):
    
    def __init__(self, execute=utils.execute, **kwargs):
        self.set_execute(execute)
    
    def set_execute(self, execute):
        self._execute = execute
        
    def create(self, context, instance_id, band, prio=1):
        classid = self.db.get_classid()
        new_id = int(classid) + 1
        new_class_id = '10:' + str(new_id)
        bands = band + 'Mbit'
        cmd = ['tc class add dev eth0 parent 10:1 classid', new_class_id, 'htb rate', bands, 'prio', prio]
        self.db.tqdisc_create(context, instance_id, new_class_id, prio, bands)
        self._execute(cmd)
        return new_class_id
        
    def get(self, context, id):
        result = self.db.tqdisc_get(context, id)
        return result
    
    def get_all(self, context):
        result = self.db.tqdisc_get_all(context)
        return result
    
    def get_by_instance_id(self, context, instance_id):
        result = self.db.tqdisc_get_by_instance_id(context, instance_id)
        return result
    
    def get_host(self, context, classid):
        return self.db.tqdisc_get_host(context, classid)
    
    def get_by_ip(self, context, ip):
        result = self.db.tqdisc_get_by_ip(context, ip)
        return result
    
    def delete(self, context, classid):
        cmd = ['tc class del dev eth0 classid ', classid]
        self._execute(cmd)
        self.db.tqdisc_delete(context, classid)

from traffic import flags
from traffic import utils
from traffic import rootwrap
from traffic.db import base
import os

class API(base.Base):
    
    def set_execute(self, execute):
        self._execute = execute
        
    def create(self, context, instance_id, band, prio=1):
        classid = self.db.get_classid(context)
        if not classid:
            classid = '10:0'
        else: 
            classid = classid[0]
        new_id = int(classid.split(':')[1]) + 1
        new_class_id = '10:' + str(new_id)
        bands = band + 'Mbit'
        cmd = ['tc class add dev eth0 parent 10:1 classid ', new_class_id, ' htb rate ', bands, ' prio ', str(prio)]
        self.db.tqdisc_create(context,
                              {'instanceid': instance_id,
                               'classid': new_class_id,
                               'prio': prio, 
                               'band': bands})
#        self._execute('tc class add dev eth0 parent 10:1 classid', new_class_id, 'htb rate', bands, 'prio', prio)
        os.system(''.join(cmd))
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
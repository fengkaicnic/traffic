
from traffic import rootwrap
from traffic import utils
from traffic import db
from traffic.db import base
import os

class API(base.Base):
    
    def set_execute(self, execute):        
        self._execute = execute
        
    def create(self, context, ip, class_id, prio=1):
        ips = ip + '/32'
        cmd = ['tc filter add dev eth0 parent 10: protocol ip prio', prio ,'u32 match ip src', ips, 'flowid', class_id]
        cmd = map(str, cmd)
        #self._execute(cmd)
        
        handle = self.db.tfilter_get_last_handle(context)
        self.db.tfilter_create(context, ip, class_id, handle, prio)
        os.system(''.join(cmd))
        
    def delete(self, context, handle, prio ):       
        handle_r = '800::' + handle
        cmd = ['tc filter del dev eth0 parent 10: prio', prio, 'handle', handle_r]
        self._execute(cmd)
        self.db.tfilter_delete_by_handle(context, handle)
    
    def get(self, context, class_id):
        result = self.db.tfilter_get_by_classid(context, class_id)
        return result
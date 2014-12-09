
from traffic import rootwrap
from traffic import utils
from traffic import db
from traffic import flags
from traffic.db import base
import os

FLAGS = flags.FLAGS

class API(base.Base):
    
    def set_execute(self, execute):        
        self._execute = execute
        
    def create(self, context, ip, class_id, instanceid, host, prio=1):
        interface = FLAGS.interface
        ips = ip + '/32'
        cmd = ['tc filter add dev br100 parent 10: protocol ip prio ', prio ,' u32 match ip src ', ips, ' flowid ', class_id]
        cmd = map(str, cmd)
        #self._execute(cmd)
        
        handle = self.db.tfilter_get_last_handle(context, host)
        if not handle:
            handle = 799
        else:
            handle = handle[0]
        self.db.tfilter_create(context, 
                               {'ip': ip, 
                                'classid': class_id,
                                'flowid': class_id, 
                                'instanceid': instanceid,
                                'handle': handle+1, 
                                'host': host,
                                'prio': prio})
        print ''.join(cmd)
        
        os.system(''.join(cmd))
        
    def delete(self, context, instanceid):       
        tfilter = self.db.tfilter_get_by_instance(context, instanceid)
        interface = FLAGS.interface
        handle_r = '800::' + str(tfilter[6])
        cmd = ['tc filter del dev br100 parent 10: prio ', tfilter[11], ' handle ', handle_r, ' u32']
        cmd = map(str, cmd)
        print ''.join(cmd)
        os.system(''.join(cmd))
#        self._execute(cmd)
        self.db.tfilter_delete_by_instance(context, instanceid)
    
    def get(self, context, class_id):
        result = self.db.tfilter_get_by_classid(context, class_id)
        return result
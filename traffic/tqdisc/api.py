
from traffic import flags
from traffic import utils
from traffic import rootwrap
from traffic.db import base
import os

class API(base.Base):
    
    def set_execute(self, execute):
        self._execute = execute
        
    def create(self, context, instance_id, band, host, mac, ip, prio=1):
        mac = mac[3:]
        cmdlist = ["ifconfig | grep ", mac, " | awk \'{print $1}\'"]
        eht = os.popen("".join(cmdlist))
        virnt = eht.read().rstrip()
        cmds = ['tc qdisc add dev ', virnt, ' handle ffff: ingress']
        cmdfil = ['tc filter add dev ', virnt, ' parent ffff: protocol ip prio 50 u32 match ip src 0.0.0.0/0 police rate ']
        cmdfil.append(band)
        cmdfil.append('Mbit burst 10k drop flowid :1')
        self.db.tqdisc_create(context,
                              {'instanceid': instance_id,
                               'classid': '',
                               'prio': prio, 
                               'host': host,
                               'ip': ip,
                               'band': band+'Mbits'})
        os.system(''.join(cmds))
        os.system(''.join(cmdfil))
        
    def create_bk(self, context, instance_id, band, mac, prio=1):
        classid = self.db.get_classid(context)
        if not classid:
            classid = '10:1'
            cmds = 'tc class add dev eth0 parent 10: classid 10:1 htb rate 1000Mbit ceil 1000Mbit'
            os.system(cmds)
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
    
    def delete(self, context, instance_id, mac):
        mac = mac[3:]
        cmdlist = ["ifconfig | grep ", mac, " | awk \'{print $1}\'"]
        eht = os.popen("".join(cmdlist))
        virnt = eht.read().rstrip()
        cmd = ['tc qdisc del dev ', virnt, ' root']
        cmds = ['tc qdisc del dev ', virnt, ' ingress']
        self.db.tqdisc_delete_by_instanceid(context, instance_id)
        os.system(''.join(cmd))
        os.system(''.join(cmds))
        
    def delete_bk(self, context, classid):
        
        cmd = ['tc class del dev eth0 classid ', classid]
        self._execute(cmd)
        self.db.tqdisc_delete(context, classid)
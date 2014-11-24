'#################################################################'
import base64
import functools
import re
import string
import time
import urllib



from traffic.compute import rpcapi as compute_rpcapi
from traffic.compute import tqdisc
from traffic.compute import tfilter

from traffic.db import base
from traffic import exception
from traffic import flags
from traffic.openstack.common import excutils
from traffic.openstack.common import importutils
from traffic.openstack.common import jsonutils
from traffic.openstack.common import log as logging
from traffic.openstack.common import timeutils
from traffic.openstack.common.gettextutils import _
from traffic import tqdisc
from traffic import tfilter
from traffic.scheduler import rpcapi as scheduler_rpcapi 
from traffic import utils
from traffic.openstack.common import cfg


class API(base.Base):
    
    def __init__(self, image_service=None, tqdisc_api=None, tfilter_api=None,
                     **kwargs):
        self.scheduler_rpcapi = scheduler_rpcapi.SchedulerAPI()
        self.compute_rpcapi = compute_rpcapi.ComputeAPI()
        self.tqdisc_api = tqdisc_api or tqdisc.API()
        self.tfilter_api = tfilter_api or tfilter.API()
            
        super(API, self).__init__(**kwargs)

         
    def create(self, context, instance_id, band, prio):
#         compute_rpcapi.create_traffic(context, ip, instance_id, band, prio)
        #self.compute_rpcapi.create_traffic(context, ip, instance_id, band, prio)
        ip = self.get_ip_by_instance(context, instance_id)
        host = self.get_host_by_instance(context, instance_id)
        mac = self.get_mac_by_instance(context, instance_id)
        self.scheduler_rpcapi.create_traffic(context, ip[0], instance_id, band, host[0], mac[0], prio)
        
    def show(self, context, instance_id):
        result = self.tqdisc_api.get_by_instance_id(context, instance_id)
        return result["band"]
    
    def list(self, context):
        results = self.tqdisc_api.get_all(context)
        traffics = []
        for result in results:
#            traffic = dict(result.iteritems())
            traffic = {'id':result[0], 'instanceid':result[5], 'ip':result[7], 'band':result[9]}
            traffics.append(traffic)
        return traffics
        
    def get_by_ip(self, context, ip):
        tfilter = self.tfilter_api.get_by_ip(context, ip)
        result = self.tqdisc_api.get_by_classid(context, tfilter["flow_id"])
        return result["band"]
        
    def delete(self, context, instance_id):
        host = self.get_host_by_instance(context, instance_id)    
        mac = self.get_mac_by_instance(context, instance_id)
        self.scheduler_rpcapi.delete_traffic(context, instance_id, host[0], mac[0])
        
    def delete_bk(self, context, instance_id):
        result = self.tqdisc_api.get_by_instance_id(context, instance_id)
        self.tqdisc_api.delete(context, result["classid"])
        tfilter = self.tfilter_api.get(context, result["classid"])
        self.tfilter_api.delete(context, tfilter["handle"], tfilter['prio'])
            
    def delete_by_ip(self, context, ip):
        result = self.tqdisc_api.get_by_ip(context, ip)
        self.tqdisc_api.delete_by_ip(context, result['classid'])
        tfilter = self.tfilter_api.get(context, result['classid'])
        self.tfilter_api.delete(context, tfilter['handle'], tfilter['prio'])
        
    def update(self, context, server_id, band):
        self.delete(context, server_id)
        self.create(context, server_id, band)
        
    def get_ip_by_instance(self, context, instanceid):
        return self.db.get_ip_by_instance(context, instanceid)
    
    def get_host_by_instance(self, context, instanceid):
        return self.db.get_host_by_instance(context, instanceid)
    
    def get_mac_by_instance(self, context, instanceid):
        return self.db.get_mac_by_instance(context, instanceid)
            
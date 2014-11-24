from webob import exc
import traffic

from traffic.api.openstack import common
from traffic.api.openstack import wsgi
from traffic.api.openstack import xmlutil
from traffic import flags
from traffic import compute
from traffic.openstack.common import log as logging

from traffic.api.openstack.compute.viewer import tqdisc

LOG = logging.getLogger(__name__)
FLAGS = flags.FLAGS

class Controller(wsgi.Controller):
    
    _view_builder_class = tqdisc.ViewBuilder
    
    def __init__(self, **kwargs):
        super(Controller, self).__init__(**kwargs)
        self._compute_api = compute.API()
    
    def _get_tqdisc(self, context, server_id):
        try:
            tqdisc = self._compute_api.get(context, server_id)
        except traffic.exception.NotFound:
            msg = ('Tqdisc does not exsit')
            raise exc.HTTPNotFound(explanation=msg)
        return tqdisc

    def create(self, req, body):
        context = req.environ['traffic.context']
        instance_id = body['instance_id']
        band = body['band']
        prio = body['prio']
        self._compute_api.create(context, instance_id, band, prio)
    
    def delete(self, req, instance_id):
        context = req.environ['traffic.context']
        self._compute_api.delete(context, instance_id)
    
    def delete_by_ip(self, req, ip, id):
        context = req.environ['traffic.context']
        self._compute_api.delete_by_ip(context, ip)
    
    def index(self, req):
        context = req.environ['traffic.context']
        result = self._compute_api.list(context)
        
        return result['band']
    
    def show(self, req, instance_id, body):
        context = req.environ['traffic.context']
        
        band = self._compute_api.show(context, instance_id)
        return band
    
    def list(self, req):
        context = req.environ['traffic.context']
        result = self._compute_api.list(context)
         
        if not result:
            return None
        
        return result
    
    def show_by_ip(self, req, ip, body):
        context = req.environ['traffic.context']
        band = self._compute_api.get_by_ip(context, ip)
        return band
def create_resource():
    
    return wsgi.Resource(Controller())
        
        
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

    def create(self, req, instance_id, body):
        context = req.environ['traffic.context']
        tbody = body['traffic']
        band = tbody['band']
        prio = tbody['prio']
        ip = tbody['ip']
        self._compute_api.create(context, ip, instance_id, band, prio)
        raise exc.HTTPNotImplemented()
    
    def delete(self, req, instance_id, id):
        context = req.environ['traffic.context']
        self._compute_api.delete(context, instance_id)
        raise exc.HTTPNotImplemented()
    
    def delete_by_ip(self, req, ip, id):
        context = req.environ['traffic.context']
        self._compute_api.delete_by_ip(context, ip)
        raise exc.HTTPNotImplemented()
    
    def index(self, req, server_id, body):
        context = req.environ['traffic.context']
        tqdisc = self._get_tqdisc(context, server_id)
        return self._view_builder.index(tqdisc)
    
    def show(self, req, instance_id, body):
        context = req.environ['traffic.context']
        
        band = self._compute_api.show(context, instance_id)
        return band
    
    def list(self, req, body):
        context = req.environ['traffic.context']
        bands = self._compute_api.list(context)
        
        return bands
    
    def show_by_ip(self, req, ip, body):
        context = req.environ['traffic.context']
        band = self._compute_api.get_by_ip(context, ip)
        return band
def create_resource():
    
    return wsgi.Resource(Controller)
        
        
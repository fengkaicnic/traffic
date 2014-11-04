from webob import exc
import traffic
from traffic import exception

from traffic.api.openstack import common
from traffic.api.openstack import wsgi
from traffic.api.openstack import xmlutil
from traffic import flags
from traffic.openstack.common import log as logging 

from traffic.api.openstack.compute.viewer import tqdisc

LOG = logging.getLogger(__name__)
FLAGS = flags.FLAGS

class Controller(wsgi.Controller):
    
    _view_builder_class = tqdisc.ViewBuilder
    
    def _get_tqdisc(self, context, server_id):
        try:
            tqdisc = self._compute_api.get(context, server_id)
        except traffic.exception.NotFound:
            msg = ('Tqdisc does not exsit')
            raise exc.HTTPNotFound(explanation=msg)
        return tqdisc
    
    def __init__(self, **kwargs):
        super(Controller, self).__init__(**kwargs)
        self.__compute_api = traffic

    def create(self, req, server_id, body):
        raise exc.HTTPNotImplemented()
    
    def delete(self, req, server_id, id):
        raise exc.HTTPNotImplemented()
    
    def index(self, req, server_id):
        context = req.environ['traffic.context']
        tqdisc = self._get_tqdisc(context, server_id)
        return self._view_builder.index(tqdisc)
    
    def show(self, req, server_id):
        context = req.environ['traffic.context']
        tqdisc = self._get_tqdisc(context, server_id)
        return self._view_builder.show(tqdisc)
    
def create_resource():
    
    return wsgi.Resource(Controller())
        
        
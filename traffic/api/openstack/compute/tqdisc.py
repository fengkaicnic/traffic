from webob import exc
import traffic

from traffic.api.openstack import common
from traffic.api.openstack import wsgi
from traffic.api.openstack import xmlutil
from traffic import flags
import trafficclient
from traffic.openstack.common import log as logging

from traffic.api.openstack.compute.viewer import tqdisc

LOG = logging.getLogger(__name__)
FLAGS = flags.FLAGS

class TqdiscClientWrapper(object):
    
    def __init__(self, context=None, host=None, port=None, use_ssl=False, version=1):
        if host is not None:
            self.client = self._create_static_client(context, host, port, use_ssl, version)
        else:
            self.client = None
        self.api_servers = None
            
    def _create_static_client(self, context, host, port, use_ssl, version):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.version = version
        return _create_tqdisc_client(context, self.host, 
                                     self.port, self.use_ssl, 
                                     self.version)
    
    def call(self):
        
def _create_tqdisc_client(context, host, port, use_ssl, version=1):
    if use_ssl:
        schemes = 'https'
    else:
        schemes = 'http'
    params = {}
    params['insecure'] = FLAGS.qdisc_api_insecure
    if FLAGS.auth_strategy == 'keystone':
        params['token'] = context.token
    endpoint = '%s://%s:%s' % (schemes, host, port)
    return trafficclient.Client(str(version), endpoint, **params)
        
class TqdiscService(object):
    
    def __init__(self, client=None):
        self._client = client or TqdiscClientWrapper()

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
    
    return wsgi.Resource(Controller)
        
        
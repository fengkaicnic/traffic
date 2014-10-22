from webob import exc
import traffic
import time

from traffic.api.openstack import common
from traffic.api.openstack import wsgi
from traffic.api.openstack import xmlutil
from traffic import flags
from traffic import exception
from traffic import compute
from traffic.openstack.common import log as logging

from traffic.api.openstack.compute.viewer import tfilter

LOG = logging.getLogger(__name__)
FLAGS = flags.FLAGS

class Controller(wsgi.Controller):
    
    _view_builder_class = tfilter.ViewBuilder
    
    def _get_tfilter(self, context, server_id):
        try:
            tfilter = self._compute_api.get(context, server_id)
        except traffic.exception.NotFound:
            msg = ('tfilter does not exsit')
            raise exc.HTTPNotFound(explanation=msg)
        return tfilter
    
    def __init__(self, ext_mgr=None, **kwargs):
        super(Controller, self).__init__(**kwargs)
        self.compute_api = compute.API()
        self.ext_mgr = ext_mgr

    def create(self, req, server_id, body):
        context = req.environ['traffic.context']
        params = req.GET.copy()
        try:
            self.compute_api.create(context, server_id)
        except(exception.NotFound):
            explanation = _("tfilter not found")
            raise webob.exc.HTTPNotFound(explanation=explanation)
        return webob.exc.HTTPNoContent()
    
    def delete(self, req, server_id, id):
        context = req.environ['traffic.context']
        params = req.GET.copy()
        try:
            self.compute_api.delete(context, server_id)
        except(exception.NotFound):
            explanation = _('tfilter not found')
            raise webob.exc.HTTPNotFound(explanation=explanation)
        return webob.exc.HTTPNotContent()
    
    def index(self, req, server_id):
        context = req.environ['traffic.context']
        tfilter = self._get_tfilter(context, server_id)
        return self._view_builder.index(tfilter)
    
    def show(self, req, server_id):
        context = req.environ['traffic.context']
        params = req.GET.copy()
        tfilter = self._get_tfilter(context, server_id)
        try:
            self.compute_api.show(context, server_id)
        except(exception.NotFound):
            explanation = _('tfilter not found')
            raise webob.exc.HTTPNotFound(explanation=explanation)
        return self._view_builder.show(tfilter)
    
def create_resource():
    
    return wsgi.Resource(Controller)
        
        

import itertools
from traffic.api.openstack import common

from traffic import flags
from traffic.openstack.common import log as logging

FLAGS = flags.FLAGS
LOG = logging.getLogger(__name__)

class ViewBuilder(common.ViewBuilder):
    
    _collection_name = 'tqdisc'
    
    def basic(self):
        return
        
    def show(self):
        return
    
    def index(self):
        return
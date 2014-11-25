
import itertools
from traffic.api.openstack import common

from traffic import flags
from traffic.openstack.common import log as logging

FLAGS = flags.FLAGS
LOG = logging.getLogger(__name__)

class ViewBuilder(common.ViewBuilder):
    
    _collection_name = 'tqdisc'
    
    def basic(self, request, traffic):
        """Generic, non-detailed view of an instance."""
        return {
            "traffic": {
                "id": traffic["id"],
                "instanceid": traffic["instanceid"]+'Mbits',
                "ip": traffic["ip"],
                "band": traffic["band"],
            },
        }

        
    def show(self):
        return
    
    def index(self, request, traffics):
        return self._list_view(self.basic, request, traffics)
    
    def _list_view(self, func, request, traffics):
        """Provide a view for a list of servers."""
        traffic_list = [func(request, traffic)["traffic"] for traffic in traffics]
        traffic_links = self._get_collection_links(request,
                                                   traffics,
                                                   self._collection_name)
        traffics_dict = dict(traffics=traffic_list)

        if traffic_links:
            traffics_dict["traffics_links"] = traffic_links

        return traffics_dict
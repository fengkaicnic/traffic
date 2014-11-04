# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
WSGI middleware for OpenStack Compute API.
"""

import traffic.api.openstack 
from traffic.api.openstack.compute import extensions
from traffic.api.openstack.compute import versions
from traffic import flags
from traffic.openstack.common import cfg
from traffic.openstack.common import log as logging
from traffic.api.openstack.compute import tfilter
from traffic.api.openstack.compute import tqdisc
from traffic.api.openstack.compute import trafficapi

LOG = logging.getLogger(__name__)

FLAGS = flags.FLAGS


class APIRouter(traffic.api.openstack.APIRouter):
    """
    Routes requests on the OpenStack API to the appropriate controller
    and method.
    """
    ExtensionManager = extensions.ExtensionManager

    def _setup_routes(self, mapper, ext_mgr):

        mapper.redirect("", "/")
        
#        self.resources['tqdisc'] = tqdisc.create_resource()
#        mapper.resource("tqdisc", "tqdiscs",
#                        controller=self.resources['tqdisc'],
#                        collection={'detail':'GET'},
#                        member={'action':'POST'}) 
        
#        self.resources['tfilter'] = tfilter.create_resource()
#        mapper.resource("tfilter", "tfilters",
#                        controller=self.resources["tfilter"],
#                        collection={'detail':'GET'},
#                        member={'action':'POST'}) 
        
#        self.resources['traffic'] = trafficapi.create_resource()
#        mapper.resource("traffic", "traffic",
#                        controller=self.resources['traffic'],
#                        collection={'detail':'GET'},
#                        member={'action':'POST'})
        
        controller = trafficapi.Controller()
        mapper.connect("traffic",
                       "/{project_id}/traffic/delete_by_ip/{}",
                       controller=controller,
                       action='delete_by_ip',
                       conditions={"delete_by_ip": 'POST'})
        
        mapper.connect("traffic",
                       "/{project_id}/traffic/list/",
                       controller=controller,
                       action='list',
                       conditions={"list":'GET'})
        
        mapper.connect("traffic",
                       "/{project_id}/traffic/show_by_ip/{ip}",
                       controller=controller,
                       action='show_by_ip',
                       conditions={"show_by_ip":'POST'})

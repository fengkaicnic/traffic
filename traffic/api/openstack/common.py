# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 OpenStack LLC.
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

import functools
import os
import re
import urlparse

import webob
from xml.dom import minidom

from traffic.api.openstack import wsgi
from traffic.api.openstack import xmlutil
from traffic.compute import utils as compute_utils 
from traffic import exception
from traffic import flags
from traffic.openstack.common import log as logging


LOG = logging.getLogger(__name__)
FLAGS = flags.FLAGS


XML_NS_V11 = 'http://docs.openstack.org/compute/api/v1.1'




def get_pagination_params(request):
    """Return marker, limit tuple from request.

    :param request: `wsgi.Request` possibly containing 'marker' and 'limit'
                    GET variables. 'marker' is the id of the last element
                    the client has seen, and 'limit' is the maximum number
                    of items to return. If 'limit' is not specified, 0, or
                    > max_limit, we default to max_limit. Negative values
                    for either marker or limit will cause
                    exc.HTTPBadRequest() exceptions to be raised.

    """
    params = {}
    if 'limit' in request.GET:
        params['limit'] = _get_limit_param(request)
    if 'marker' in request.GET:
        params['marker'] = _get_marker_param(request)
    if 'page_index' in request.GET:
        params['page_index'] = _get_page_index_param(request)
    return params

#add by weiyuanke@cnic.cn
def _get_page_index_param(request):
    """Extract integer page_index from request or fail"""
    try:
        page_index = int(request.GET['page_index'])
    except ValueError:
        msg = _('page_index param must be an integer')
        raise webob.exc.HTTPBadRequest(explanation=msg)
    if page_index < 0:
        msg = _('page_index param must be positive')
        raise webob.exc.HTTPBadRequest(explanation=msg)
    return page_index



def _get_limit_param(request):
    """Extract integer limit from request or fail"""
    try:
        limit = int(request.GET['limit'])
    except ValueError:
        msg = _('limit param must be an integer')
        raise webob.exc.HTTPBadRequest(explanation=msg)
    if limit < 0:
        msg = _('limit param must be positive')
        raise webob.exc.HTTPBadRequest(explanation=msg)
    return limit


def _get_marker_param(request):
    """Extract marker id from request or fail"""
    return request.GET['marker']


#added by weiyuanke@cnic.cn
def get_page_index(request):
    params = get_pagination_params(request)
    page_index = params.get('page_index')
    return page_index


def get_id_from_href(href):
    """Return the id or uuid portion of a url.

    Given: 'http://www.foo.com/bar/123?q=4'
    Returns: '123'

    Given: 'http://www.foo.com/bar/abc123?q=4'
    Returns: 'abc123'

    """
    return urlparse.urlsplit("%s" % href).path.split('/')[-1]


def remove_version_from_href(href):
    """Removes the first api version from the href.

    Given: 'http://www.traffic.com/v1.1/123'
    Returns: 'http://www.traffic.com/123'

    Given: 'http://www.traffic.com/v1.1'
    Returns: 'http://www.traffic.com'

    """
    parsed_url = urlparse.urlsplit(href)
    url_parts = parsed_url.path.split('/', 2)

    # NOTE: this should match vX.X or vX
    expression = re.compile(r'^v([0-9]+|[0-9]+\.[0-9]+)(/.*|$)')
    if expression.match(url_parts[1]):
        del url_parts[1]

    new_path = '/'.join(url_parts)

    if new_path == parsed_url.path:
        msg = _('href %s does not contain version') % href
        LOG.debug(msg)
        raise ValueError(msg)

    parsed_url = list(parsed_url)
    parsed_url[2] = new_path
    return urlparse.urlunsplit(parsed_url)

def dict_to_query_str(params):
    # TODO(throughnothing): we should just use urllib.urlencode instead of this
    # But currently we don't work with urlencoded url's
    param_str = ""
    for key, val in params.iteritems():
        param_str = param_str + '='.join([str(key), str(val)]) + '&'

    return param_str.rstrip('&')


def get_networks_for_instance_from_nw_info(nw_info):
    networks = {}
    for vif in nw_info:
        ips = vif.fixed_ips()
        floaters = vif.floating_ips()
        label = vif['network']['label']
        if label not in networks:
            networks[label] = {'ips': [], 'floating_ips': []}

        networks[label]['ips'].extend(ips)
        networks[label]['floating_ips'].extend(floaters)
    return networks

def raise_http_conflict_for_instance_invalid_state(exc, action):
    """Return a webob.exc.HTTPConflict instance containing a message
    appropriate to return via the API based on the original
    InstanceInvalidState exception.
    """
    attr = exc.kwargs.get('attr')
    state = exc.kwargs.get('state')
    if attr and state:
        msg = _("Cannot '%(action)s' while instance is in %(attr)s %(state)s")
    else:
        # At least give some meaningful message
        msg = _("Instance is in an invalid state for '%(action)s'")
    raise webob.exc.HTTPConflict(explanation=msg % locals())


class MetadataDeserializer(wsgi.MetadataXMLDeserializer):
    def deserialize(self, text):
        dom = minidom.parseString(text)
        metadata_node = self.find_first_child_named(dom, "metadata")
        metadata = self.extract_metadata(metadata_node)
        return {'body': {'metadata': metadata}}


class MetaItemDeserializer(wsgi.MetadataXMLDeserializer):
    def deserialize(self, text):
        dom = minidom.parseString(text)
        metadata_item = self.extract_metadata(dom)
        return {'body': {'meta': metadata_item}}


class MetadataXMLDeserializer(wsgi.XMLDeserializer):

    def extract_metadata(self, metadata_node):
        """Marshal the metadata attribute of a parsed request"""
        if metadata_node is None:
            return {}
        metadata = {}
        for meta_node in self.find_children_named(metadata_node, "meta"):
            key = meta_node.getAttribute("key")
            metadata[key] = self.extract_text(meta_node)
        return metadata

    def _extract_metadata_container(self, datastring):
        dom = minidom.parseString(datastring)
        metadata_node = self.find_first_child_named(dom, "metadata")
        metadata = self.extract_metadata(metadata_node)
        return {'body': {'metadata': metadata}}

    def create(self, datastring):
        return self._extract_metadata_container(datastring)

    def update_all(self, datastring):
        return self._extract_metadata_container(datastring)

    def update(self, datastring):
        dom = minidom.parseString(datastring)
        metadata_item = self.extract_metadata(dom)
        return {'body': {'meta': metadata_item}}


metadata_nsmap = {None: xmlutil.XMLNS_V11}


class MetaItemTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        sel = xmlutil.Selector('meta', xmlutil.get_items, 0)
        root = xmlutil.TemplateElement('meta', selector=sel)
        root.set('key', 0)
        root.text = 1
        return xmlutil.MasterTemplate(root, 1, nsmap=metadata_nsmap)


class MetadataTemplateElement(xmlutil.TemplateElement):
    def will_render(self, datum):
        return True


class MetadataTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = MetadataTemplateElement('metadata', selector='metadata')
        elem = xmlutil.SubTemplateElement(root, 'meta',
                                          selector=xmlutil.get_items)
        elem.set('key', 0)
        elem.text = 1
        return xmlutil.MasterTemplate(root, 1, nsmap=metadata_nsmap)


def check_snapshots_enabled(f):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        if not FLAGS.allow_instance_snapshots:
            LOG.warn(_('Rejecting snapshot request, snapshots currently'
                       ' disabled'))
            msg = _("Instance snapshots are not permitted at this time.")
            raise webob.exc.HTTPBadRequest(explanation=msg)
        return f(*args, **kwargs)
    return inner


class ViewBuilder(object):
    """Model API responses as dictionaries."""

    def _get_links(self, request, identifier, collection_name):
        return [{
            "rel": "self",
            "href": self._get_href_link(request, identifier, collection_name),
        },
        {
            "rel": "bookmark",
            "href": self._get_bookmark_link(request,
                                            identifier,
                                            collection_name),
        }]

    def _get_next_link(self, request, identifier, collection_name):
        """Return href string with proper limit and marker params."""
        params = request.params.copy()
        params["marker"] = identifier
        prefix = self._update_link_prefix(request.application_url,
                                          FLAGS.osapi_compute_link_prefix)
        url = os.path.join(prefix,
                           request.environ["traffic.context"].project_id,
                           collection_name)
        return "%s?%s" % (url, dict_to_query_str(params))

    def _get_href_link(self, request, identifier, collection_name):
        """Return an href string pointing to this object."""
        prefix = self._update_link_prefix(request.application_url,
                                          FLAGS.osapi_compute_link_prefix)
        return os.path.join(prefix,
                            request.environ["traffic.context"].project_id,
                            collection_name,
                            str(identifier))

    def _get_bookmark_link(self, request, identifier, collection_name):
        """Create a URL that refers to a specific resource."""
        base_url = remove_version_from_href(request.application_url)
        base_url = self._update_link_prefix(base_url,
                                            FLAGS.osapi_compute_link_prefix)
        return os.path.join(base_url,
                            request.environ["traffic.context"].project_id,
                            collection_name,
                            str(identifier))

    def _get_collection_links(self,
                              request,
                              items,
                              collection_name,
                              id_key="uuid"):
        """Retrieve 'next' link, if applicable."""
        links = []
        limit = int(request.params.get("limit", 0))
        if limit and limit == len(items):
            last_item = items[-1]
            if id_key in last_item:
                last_item_id = last_item[id_key]
            elif 'id' in last_item:
                last_item_id = last_item["id"]
            else:
                last_item_id = last_item["flavorid"]
            links.append({
                "rel": "next",
                "href": self._get_next_link(request,
                                            last_item_id,
                                            collection_name),
            })
        return links

    def _update_link_prefix(self, orig_url, prefix):
        if not prefix:
            return orig_url
        url_parts = list(urlparse.urlsplit(orig_url))
        prefix_parts = list(urlparse.urlsplit(prefix))
        url_parts[0:2] = prefix_parts[0:2]
        return urlparse.urlunsplit(url_parts)

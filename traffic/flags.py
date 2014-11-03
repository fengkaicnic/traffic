# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# Copyright 2012 Red Hat, Inc.
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

"""Command-line flag library.

Emulates gflags by wrapping cfg.ConfigOpts.

The idea is to move fully to cfg eventually, and this wrapper is a
stepping stone.

"""

import os
import socket
import sys

from traffic.openstack.common import cfg


FLAGS = cfg.CONF


def parse_args(argv, default_config_files=None):
    FLAGS.disable_interspersed_args()
    return argv[:1] + FLAGS(argv[1:],
                            project='traffic',
                            default_config_files=default_config_files)


class UnrecognizedFlag(Exception):
    pass


def DECLARE(name, module_string, flag_values=FLAGS):
    if module_string not in sys.modules:
        __import__(module_string, globals(), locals())
    if name not in flag_values:
        raise UnrecognizedFlag('%s not defined by %s' % (name, module_string))


def _get_my_ip():
    """
    Returns the actual ip of the local machine.

    This code figures out what source address would be used if some traffic
    were to be sent out to some well known address on the Internet. In this
    case, a Google DNS server is used, but the specific address does not
    matter much.  No traffic is actually sent.
    """
    try:
        csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        csock.connect(('8.8.8.8', 80))
        (addr, port) = csock.getsockname()
        csock.close()
        return addr
    except socket.error:
        return "127.0.0.1"


core_opts = [
    cfg.StrOpt('connection_type',
               default=None,
               help='Deprecated (use compute_driver instead): Virtualization '
                    'api connection type : libvirt, xenapi, or fake'),
    cfg.StrOpt('sql_connection',
               default='sqlite:///$state_path/$sqlite_db',
               help='The SQLAlchemy connection string used to connect to the '
                    'database'),
    cfg.StrOpt('api_paste_config',
               default="api-paste.ini",
               help='File name for the paste.deploy config for traffic-api'),
    ]

debug_opts = [
    cfg.BoolOpt('fake_network',
                default=False,
                help='If passed, use fake network devices and addresses'),
    cfg.IntOpt('sql_connection_debug',
               default=0,
               help='Verbosity of SQL debugging information. 0=None, '
                    '100=Everything'),
    cfg.BoolOpt('sql_connection_trace',
               default=False,
               help='Add python stack traces to SQL as comment strings'),
]

FLAGS.register_cli_opts(core_opts)
FLAGS.register_cli_opts(debug_opts)

global_opts = [

    cfg.StrOpt('traffic_manager',
               default='traffic.compute.manager.TrafficManager',
               help='full class name for the Manager for compute'),

    cfg.StrOpt('root_helper',
               default='sudo',
               help='Deprecated: command to use for running commands as root'),
    cfg.StrOpt('rootwrap_config',
               default=None,
               help='Path to the rootwrap configuration file to use for '
                    'running commands as root'),
    cfg.MultiStrOpt('osapi_compute_extension',
                    default=[
                      'traffic.api.openstack.compute.contrib.standard_extensions'
                      ],
                    help='osapi compute extension to load'),
    cfg.BoolOpt('monkey_patch',
                default=False,
                help='Whether to log monkey patching'),
               
    cfg.StrOpt('scheduler_topic',
               default='scheduler',
               help='the topic scheduler nodes listen on'),
    
    cfg.StrOpt('host',
               default=socket.gethostname(),
               help='Name of this node.  This can be an opaque identifier.  '
                    'It is not necessarily a hostname, FQDN, or IP address. '
                    'However, the node name must be valid within '
                    'an AMQP key, and if using ZeroMQ, a valid '
                    'hostname, FQDN, or IP address'),

    cfg.StrOpt('traffic_api_class',
                default='traffic.compute.api.API',
                help='The full class name of the compute API class to use'),
            
    cfg.StrOpt('tqdisc_api_class',
               default='traffic.tqdisc.api.API',
               help='The full class name of the tqdisc API class to use'),
        
    cfg.StrOpt('tfilter_api_class',
               default='traffic.tfilter.api.API',
               help='The full class name of the tfilter API class to use'),

    cfg.StrOpt('auth_strategy',
               default='keystone',
               help='The strategy to use for auth: noauth or keystone.'),

]

FLAGS.register_opts(global_opts)

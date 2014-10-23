# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 OpenStack, LLC.
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

"""Compute-related Utilities and helpers."""

import re
import string
import traceback

from traffic import db
from traffic import exception
from traffic import flags

from traffic.openstack.common import log
from traffic.openstack.common.notifier import api as notifier_api
from traffic import utils

FLAGS = flags.FLAGS
LOG = log.getLogger(__name__)


def add_instance_fault_from_exc(context, instance_uuid, fault, exc_info=None):
    """Adds the specified fault to the database."""

    code = 500
    if hasattr(fault, "kwargs"):
        code = fault.kwargs.get('code', 500)

    details = unicode(fault)
    if exc_info and code == 500:
        tb = exc_info[2]
        details += '\n' + ''.join(traceback.format_tb(tb))

    values = {
        'instance_uuid': instance_uuid,
        'code': code,
        'message': fault.__class__.__name__,
        'details': unicode(details),
    }
    db.instance_fault_create(context, values)




def _get_unused_letters(used_letters):
    doubles = [first + second for second in string.ascii_lowercase
               for first in string.ascii_lowercase]
    all_letters = set(list(string.ascii_lowercase) + doubles)
    letters = list(all_letters - used_letters)
    # NOTE(vish): prepend ` so all shorter sequences sort first
    letters.sort(key=lambda x: x.rjust(2, '`'))
    return letters[0]



def has_audit_been_run(context, host, timestamp=None):
    begin, end = utils.last_completed_audit_period(before=timestamp)
    task_log = db.task_log_get(context, "instance_usage_audit",
                               begin, end, host)
    if task_log:
        return True
    else:
        return False


def start_instance_usage_audit(context, begin, end, host, num_instances):
    db.task_log_begin_task(context, "instance_usage_audit", begin, end, host,
                           num_instances, "Instance usage audit started...")


def finish_instance_usage_audit(context, begin, end, host, errors, message):
    db.task_log_end_task(context, "instance_usage_audit", begin, end, host,
                         errors, message)

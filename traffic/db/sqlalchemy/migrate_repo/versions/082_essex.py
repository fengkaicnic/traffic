# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

from migrate import ForeignKeyConstraint
from sqlalchemy import Boolean, BigInteger, Column, DateTime, Float, ForeignKey
from sqlalchemy import Index, Integer, MetaData, String, Table, Text

from nova import flags
from nova.openstack.common import log as logging

FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)


# Note on the autoincrement flag: this is defaulted for primary key columns
# of integral type, so is no longer set explicitly in such cases.

def upgrade(migrate_engine):
    meta = MetaData()
    meta.bind = migrate_engine
    
    tfilter = Table('tfilter', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', Integer, primary_key=True, nullable=False),
        Column('classid', String(length=10)),
        Column('host', String(length=50)),
        Column('instanceid', String(length=50)),
        Column('handle', Integer),
        Column('ip', String(length=25)),
        Column('flowid', String(length=10)),
        Column('prio', Integer),
        mysql_engine='InnoDB',)
    
    tqdisc = Table('tqdisc', meta,
        Column('created_at', DateTime),
        Column('updated_at', DateTime),
        Column('deleted_at', DateTime),
        Column('deleted', Boolean),
        Column('id', Integer, primary_key=True, nullable=False),
        Column('instanceid', String(length=50)),
        Column('host', String(length=50)),
        Column('classid', String(length=20)),
        Column('band', Integer),
        Column('ip', String(length=25)),
        Column('prio', Integer),
        mysql_engine='InnoDB',)

    # create all tables
    tables = [tqdisc, tfilter]

    for table in tables:
        try:
            table.create()
        except Exception:
            LOG.info(repr(table))
            LOG.exception('Exception while creating table.')
            raise

    # MySQL specific Indexes from Essex
    # NOTE(dprince): I think some of these can be removed in Folsom
    indexes = [
        Index('instanceid', tqdisc.c.instanceid),
        Index('instanceid', tfilter.c.instanceid),
    ]

    if migrate_engine.name == 'mysql':
        for index in indexes:
            index.create(migrate_engine)

    # Hopefully this entire loop to set the charset can go away during
    # the "E" release compaction. See the notes on the dns_domains
    # table above for why this is required vs. setting mysql_charset inline.
    if migrate_engine.name == "mysql":
        tables = [
            # tables that are FK parents, must be converted early
            "tfilter", "tqdisc"]
        sql = "SET foreign_key_checks = 0;"
        for table in tables:
            sql += "ALTER TABLE %s CONVERT TO CHARACTER SET utf8;" % table
        sql += "SET foreign_key_checks = 1;"
        sql += "ALTER DATABASE %s DEFAULT CHARACTER SET utf8;" \
            % migrate_engine.url.database
        migrate_engine.execute(sql)

    if migrate_engine.name == "postgresql":
        # NOTE(dprince): Need to rename the leftover zones stuff.
        # https://bugs.launchpad.net/nova/+bug/993667
        sql = "ALTER TABLE cells_id_seq RENAME TO zones_id_seq;"
        sql += "ALTER TABLE ONLY cells DROP CONSTRAINT cells_pkey;"
        sql += "ALTER TABLE ONLY cells ADD CONSTRAINT zones_pkey" \
                   " PRIMARY KEY (id);"

        # NOTE(dprince): Need to rename the leftover quota_new stuff.
        # https://bugs.launchpad.net/nova/+bug/993669
        sql += "ALTER TABLE quotas_id_seq RENAME TO quotas_new_id_seq;"
        sql += "ALTER TABLE ONLY quotas DROP CONSTRAINT quotas_pkey;"
        sql += "ALTER TABLE ONLY quotas ADD CONSTRAINT quotas_new_pkey" \
                   " PRIMARY KEY (id);"

        migrate_engine.execute(sql)

def downgrade(migrate_engine):
    LOG.exception('Downgrade from Essex is unsupported.')

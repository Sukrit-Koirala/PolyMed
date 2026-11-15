"""Initial, frozen relational schema for all three stores.

Revision ID: 0001
"""
import json
from pathlib import Path

from alembic import context, op
from sqlalchemy import Boolean, Column, ForeignKeyConstraint, Index, Integer, JSON, MetaData, String, Table, UniqueConstraint

revision = '0001'
down_revision = None


def frozen_metadata():
    # Snapshot is versioned with this migration; later model edits cannot alter 0001.
    schema = json.loads(Path(__file__).with_name('0001_schema.json').read_text())
    metadata = MetaData()
    target = context.get_x_argument(as_dictionary=True).get('target', 'shared')
    for name, definition in schema['shared' if target == 'shared' else 'local'].items():
        columns = []
        constraints = []
        for c in definition['columns']:
            data_type = {'String': String, 'Integer': Integer, 'Boolean': Boolean, 'JSON': JSON}[c['type']]
            columns.append(Column(c['name'], data_type, primary_key=c['primary_key'], nullable=c['nullable']))
        for fk in definition['foreign_keys']:
            constraints.append(ForeignKeyConstraint(fk['columns'], fk['references']))
        for unique in definition['unique']:
            constraints.append(UniqueConstraint(*unique))
        table = Table(name, metadata, *columns, *constraints)
        for index in definition['indexes']:
            Index(index['name'], *[table.c[c] for c in index['columns']], unique=index['unique'])
    return metadata


def upgrade():
    frozen_metadata().create_all(op.get_bind())


def downgrade():
    frozen_metadata().drop_all(op.get_bind())

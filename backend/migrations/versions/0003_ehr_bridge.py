"""EHR Bridge sessions, patient accounts, scoped approval and exchange evidence.

Revision ID: 0003
"""
import json
from pathlib import Path
from alembic import context, op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'


def upgrade():
    if context.get_x_argument(as_dictionary=True).get('target', 'shared') != 'shared':
        return
    schema = json.loads(Path(__file__).with_name('0003_schema.json').read_text())
    metadata = sa.MetaData()
    for name, definition in schema.items():
        columns = [sa.Column(c['name'], {'String': sa.String, 'Integer': sa.Integer, 'Boolean': sa.Boolean, 'JSON': sa.JSON}[c['type']], primary_key=c['primary_key'], nullable=c['nullable']) for c in definition['columns']]
        constraints = [sa.ForeignKeyConstraint(f['columns'], f['references']) for f in definition['foreign_keys']]
        constraints += [sa.UniqueConstraint(*u) for u in definition['unique']]
        table = sa.Table(name, metadata, *columns, *constraints)
        for index in definition['indexes']:
            sa.Index(index['name'], *[table.c[c] for c in index['columns']], unique=index['unique'])
    metadata.create_all(op.get_bind(), tables=[t for t in metadata.sorted_tables if t.name.startswith('bridge_')])


def downgrade():
    raise RuntimeError('Restore a verified backup; do not erase consent and clinical history evidence')

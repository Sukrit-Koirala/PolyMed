"""Hospital memberships, patient registration, note drafts and review decisions.

Revision ID: 0002
"""
from datetime import datetime, timezone

from alembic import context, op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'


def add_if_missing(table, column):
    if column.name not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}:
        with op.batch_alter_table(table) as batch:
            batch.add_column(column)


def upgrade():
    target = context.get_x_argument(as_dictionary=True).get('target', 'shared')
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if target == 'shared':
        add_if_missing('sessions', sa.Column('active_hospital_id', sa.String(), sa.ForeignKey('hospitals.id', name='fk_session_workspace'), nullable=True))
        add_if_missing('identity_review_candidates', sa.Column('target_patient_id', sa.String(), sa.ForeignKey('patient_links.id', name='fk_identity_target'), nullable=True))
        if 'hospital_memberships' not in tables:
            op.create_table('hospital_memberships', sa.Column('id', sa.String(), primary_key=True), sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False, index=True), sa.Column('hospital_id', sa.String(), sa.ForeignKey('hospitals.id'), nullable=False), sa.Column('role', sa.String(), nullable=False), sa.Column('active', sa.Boolean(), nullable=False), sa.UniqueConstraint('user_id', 'hospital_id'))
        if 'conflict_reviews' not in tables:
            op.create_table('conflict_reviews', sa.Column('id', sa.String(), primary_key=True), sa.Column('conflict_id', sa.String(), sa.ForeignKey('clinical_conflicts.id'), nullable=False), sa.Column('hospital_id', sa.String(), sa.ForeignKey('hospitals.id'), nullable=False), sa.Column('status', sa.String(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False), sa.Column('reviewed_fingerprint', sa.String(), nullable=False), sa.UniqueConstraint('conflict_id', 'hospital_id'))
        if 'conflict_review_decisions' not in tables:
            op.create_table('conflict_review_decisions', sa.Column('id', sa.String(), primary_key=True), sa.Column('conflict_review_id', sa.String(), sa.ForeignKey('conflict_reviews.id'), nullable=False, index=True), sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False), sa.Column('status', sa.String(), nullable=False), sa.Column('note', sa.String(), nullable=False), sa.Column('created_at', sa.String(), nullable=False))
        # Migrate existing accounts without changing passwords or primary hospital scope.
        connection = op.get_bind()
        users = connection.execute(sa.text('SELECT id, hospital_id, role FROM users')).mappings().all()
        for user in users:
            exists = connection.execute(sa.text('SELECT id FROM hospital_memberships WHERE user_id=:user AND hospital_id=:hospital'), {'user': user['id'], 'hospital': user['hospital_id']}).first()
            if not exists:
                connection.execute(sa.text('INSERT INTO hospital_memberships (id,user_id,hospital_id,role,active) VALUES (:id,:user,:hospital,:role,:active)'), {'id': f"migrated-{user['id']}", 'user': user['id'], 'hospital': user['hospital_id'], 'role': user['role'], 'active': True})
        connection.execute(sa.text('UPDATE sessions SET active_hospital_id=(SELECT hospital_id FROM users WHERE users.id=sessions.user_id) WHERE active_hospital_id IS NULL'))
    else:
        timestamp = datetime.now(timezone.utc).isoformat()
        defaults = {'first_name': '', 'last_name': '', 'administrative_gender': 'unknown', 'contact': '', 'care_status': 'active', 'created_at': timestamp, 'updated_at': timestamp}
        for name, default in defaults.items():
            add_if_missing('patients', sa.Column(name, sa.String(), nullable=False, server_default=default))
        if 'clinical_note_drafts' not in tables:
            op.create_table('clinical_note_drafts', sa.Column('id', sa.String(), primary_key=True), sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False, index=True), sa.Column('author_id', sa.String(), nullable=False), sa.Column('author_name', sa.String(), nullable=False), sa.Column('title', sa.String(), nullable=False), sa.Column('transcript', sa.String(), nullable=True), sa.Column('transcript_expires_at', sa.String(), nullable=True), sa.Column('sections', sa.JSON(), nullable=False), sa.Column('status', sa.String(), nullable=False), sa.Column('revision', sa.Integer(), nullable=False), sa.Column('generation_provider', sa.String(), nullable=False), sa.Column('generation_warnings', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(), nullable=False), sa.Column('updated_at', sa.String(), nullable=False), sa.Column('approved_by', sa.String(), nullable=True), sa.Column('approved_at', sa.String(), nullable=True), sa.Column('record_id', sa.String(), sa.ForeignKey('clinical_records.id'), nullable=True))
        if 'patient_timeline_events' not in tables:
            op.create_table('patient_timeline_events', sa.Column('id', sa.String(), primary_key=True), sa.Column('patient_id', sa.String(), sa.ForeignKey('patients.id'), nullable=False, index=True), sa.Column('event_type', sa.String(), nullable=False), sa.Column('description', sa.String(), nullable=False), sa.Column('author', sa.String(), nullable=False), sa.Column('occurred_at', sa.String(), nullable=False), sa.Column('record_id', sa.String(), sa.ForeignKey('clinical_records.id'), nullable=True))


def downgrade():
    # Deliberately avoid a downgrade that could erase approved-note or patient evidence.
    raise RuntimeError('Restore a verified pre-migration backup to downgrade this clinical data schema')

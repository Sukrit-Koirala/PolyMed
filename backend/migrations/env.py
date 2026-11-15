from alembic import context
from sqlalchemy import create_engine

from backend.app.config import Settings
from backend.app.models import LocalBase, SharedBase

settings = Settings()
target = context.get_x_argument(as_dictionary=True).get('target', 'shared')
urls = {'shared': settings.shared_url, **settings.hospital_urls}
if target not in urls:
    raise ValueError('Migration target must be shared or a configured hospital identifier')
metadata = SharedBase.metadata if target == 'shared' else LocalBase.metadata

if context.is_offline_mode():
    context.configure(url=urls[target], target_metadata=metadata, literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(urls[target]).connect() as connection:
        context.configure(connection=connection, target_metadata=metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

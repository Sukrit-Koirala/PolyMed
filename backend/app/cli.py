"""Local operational commands. Reset goes through the same guarded API as the UI."""
import argparse

from alembic import command
from alembic.config import Config

from .config import Settings
from .database import Databases
from .seed import seed
from .services import SynchronizationService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['migrate', 'seed', 'sync'])
    args = parser.parse_args()
    settings = Settings()
    if args.action == 'migrate':
        for target in ('shared', *settings.hospital_urls):
            config = Config('backend/alembic.ini')
            config.cmd_opts = argparse.Namespace(x=[f'target={target}'])
            command.upgrade(config, 'head')
            print(f'{target}: migrations applied')
        return
    if not settings.demo_mode:
        parser.error('Seed and synchronization commands require DEMO_MODE=true')
    db = Databases(settings)
    try:
        if args.action == 'seed':
            print('Synthetic fixtures seeded' if seed(db) else 'Synthetic fixtures already present')
        else:
            for hospital in db.local_factories:
                print(SynchronizationService(db).run(hospital))
    finally:
        db.dispose()


if __name__ == '__main__':
    main()

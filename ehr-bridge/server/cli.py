import argparse,json,socket,sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from .db import Database,ROOT
from .seed import populate

def main():
    parser=argparse.ArgumentParser(description='Populate only this clean EHR Bridge prototype.')
    parser.add_argument('action',choices=['seed','reset','inspect'])
    parser.add_argument('--patients',type=int,default=8)
    parser.add_argument('--confirm',default='')
    parser.add_argument('--data-dir')
    args=parser.parse_args()
    if not 2<=args.patients<=500:parser.error('Choose 2–500 fictional patients')
    db=Database(args.data_dir)
    if args.action=='reset':
        if args.confirm!='RESET-DEMO':parser.error('Use --confirm RESET-DEMO; stop the server first')
        if not db.directory.is_relative_to(ROOT):parser.error('Reset only permits this project’s own data directory')
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',8200))==0:parser.error('Stop the API on port 8200 before resetting')
        backup=(ROOT/'.data'/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')).resolve()
        if not backup.is_relative_to(ROOT):parser.error('Backup directory must remain inside this project')
        backup.mkdir(parents=True,exist_ok=False)
        paths=[]
        for name in ('central.sqlite3','memorial.sqlite3','valley.sqlite3'):
            path=(db.directory/name).resolve()
            if not path.is_relative_to(db.directory):parser.error('Invalid reset path')
            paths.append(path)
        # Finish and validate every backup before removing any of the old database files.
        for path in paths:
            if path.exists():
                with closing(sqlite3.connect(path)) as src,closing(sqlite3.connect(backup/path.name)) as dst:
                    src.backup(dst)
                    if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Backup validation failed; reset cancelled')
        print('Previous demo backed up to',backup)
        (backup/'README.txt').write_text('EHR Bridge database backup before demo replacement\n'
            +'Source directory: '+str(db.directory)+'\n'
            +'All existing SQLite backups passed PRAGMA integrity_check before replacement.\n'
            +'To restore: stop EHR Bridge; copy central.sqlite3, memorial.sqlite3 and valley.sqlite3\n'
            +'from this backup directory to the source directory, then restart the app.\n',encoding='utf-8')
        for path in paths:
            if path.exists():path.unlink()
    db.initialize()
    if args.action in ('seed','reset'):print(json.dumps(populate(db,args.patients),indent=2))
    with db.connect() as c:
        print(json.dumps({table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('hospitals','patients','visits','versions','requests','transfers')},indent=2))

if __name__=='__main__':main()

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
        backup=ROOT/'.data'/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S');backup.mkdir(parents=True,exist_ok=True)
        for name in ('central.sqlite3','memorial.sqlite3','valley.sqlite3'):
            path=(db.directory/name).resolve()
            if not path.is_relative_to(db.directory):parser.error('Invalid reset path')
            if path.exists():
                with closing(sqlite3.connect(path)) as src,closing(sqlite3.connect(backup/name)) as dst:src.backup(dst)
                path.unlink()
        print('Previous demo backed up to',backup)
    db.initialize()
    if args.action in ('seed','reset'):print(json.dumps(populate(db,args.patients),indent=2))
    with db.connect() as c:
        print(json.dumps({table:c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('hospitals','patients','visits','versions','requests','transfers')},indent=2))

if __name__=='__main__':main()

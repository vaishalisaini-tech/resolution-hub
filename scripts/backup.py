import os,sys,sqlite3
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
if len(sys.argv)!=2:raise SystemExit('Usage: python scripts/backup.py /secure/path/backup.db')
src=Path(os.getenv('DATABASE_PATH','data/hub-v3.db'));dst=Path(sys.argv[1])
if not src.exists() or dst.exists() or src.resolve()==dst.resolve():raise SystemExit('Missing source or unsafe/existing destination')
dst.parent.mkdir(parents=True,exist_ok=True)
with sqlite3.connect(src) as a,sqlite3.connect(dst) as b:
    a.backup(b)
    if b.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('Integrity check failed')
os.chmod(dst,0o600)
print('Database backup created, including stored attachments. Back up logo/config separately; encrypt and restrict all backups.')

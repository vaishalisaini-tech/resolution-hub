"""Create the first Administrator interactively. No shipped/default passwords."""
import sys,os,uuid,time,json,getpass,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
if not (root/'.env').exists() and not os.getenv('DATABASE_PATH'):shutil.copy(root/'.env.example',root/'.env');os.chmod(root/'.env',0o600)
from app.db import init,db,audit
from app.security import hash_password
init()
with db() as c:
    if c.execute("SELECT 1 FROM users WHERE role='Administrator'").fetchone():raise SystemExit('Administrator already exists. Use Admin or scripts/reset_admin.py.')
username=input('Administrator username: ').strip().lower()
import re
if not re.fullmatch('[a-z0-9_.-]{2,40}',username):raise SystemExit('Invalid username')
password=getpass.getpass('Password (15-128 characters): ')
if password!=getpass.getpass('Confirm password: '):raise SystemExit('Passwords do not match')
uid=str(uuid.uuid4())
with db() as c:
    c.execute('INSERT INTO users(id,username,display_name,password,role,workspaces,active,must_change,created) VALUES(?,?,?,?,?,?,?,?,?)',(uid,username,username,hash_password(password),'Administrator','["*"]',1,0,time.time()));audit(c,uid,'bootstrap.admin')
print('Administrator created. Start the app from this project directory. No sample knowledge was added.')

"""Local operator recovery; requires trusted server/database access."""
import sys,os,getpass
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root);sys.path.insert(0,str(root))
from app.db import db,audit
from app.security import hash_password
name=input('Existing Administrator username: ').strip()
pw=getpass.getpass('New password (15-128 characters): ')
if pw!=getpass.getpass('Confirm: '):raise SystemExit('Mismatch')
with db() as c:
    r=c.execute("SELECT id FROM users WHERE username=? AND role='Administrator'",(name,)).fetchone()
    if not r:raise SystemExit('Administrator not found')
    c.execute('UPDATE users SET password=?,active=1,must_change=0 WHERE id=?',(hash_password(pw),r['id']));c.execute('DELETE FROM sessions WHERE user_id=?',(r['id'],));audit(c,'local-operator','admin.recovery',r['id'])
print('Password reset and sessions revoked. Protect operator access.')

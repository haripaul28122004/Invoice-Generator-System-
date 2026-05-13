import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB = 'database.db'
EMAIL = 'haripaul282004@gmail.com'
PASSWORD = 'haripaul123'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

row = cur.execute('SELECT * FROM users WHERE email = ?', (EMAIL,)).fetchone()
hashed = generate_password_hash(PASSWORD)

if row:
    cur.execute(
        'UPDATE users SET username=?, password=?, role=? WHERE email=?',
        ('Hari Paul', hashed, 'user', EMAIL)
    )
    print('[UPDATED] Row id={} — password hash refreshed, role=user'.format(row['id']))
else:
    cur.execute(
        'INSERT INTO users (username, email, password, role) VALUES (?,?,?,?)',
        ('Hari Paul', EMAIL, hashed, 'user')
    )
    print('[INSERTED] New employee user created')

conn.commit()

# Verify round-trip
row = cur.execute(
    'SELECT id, username, email, role, password FROM users WHERE email=?',
    (EMAIL,)
).fetchone()
hash_ok = check_password_hash(row['password'], PASSWORD)
print('[VERIFY] id={} | email={} | role={} | hash_ok={}'.format(
    row['id'], row['email'], row['role'], hash_ok
))
conn.close()

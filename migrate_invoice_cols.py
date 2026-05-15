import sqlite3

conn = sqlite3.connect('database.db')
cur = conn.cursor()

cur.execute('PRAGMA table_info(invoices)')
cols = [r[1] for r in cur.fetchall()]
print('Before:', cols)

new_cols = [
    ('customer_email',   'TEXT DEFAULT ""'),
    ('customer_address', 'TEXT DEFAULT ""'),
    ('gst_rate',         'REAL DEFAULT 0.18'),
    ('gst_amount',       'REAL DEFAULT 0'),
]

for col, typedef in new_cols:
    if col not in cols:
        cur.execute('ALTER TABLE invoices ADD COLUMN {} {}'.format(col, typedef))
        print('  Added:', col)
    else:
        print('  Already exists:', col)

conn.commit()
cur.execute('PRAGMA table_info(invoices)')
print('After:', [r[1] for r in cur.fetchall()])
conn.close()

import sqlite3

DATABASE = 'database.db'

conn = sqlite3.connect(DATABASE)
cur = conn.cursor()
cur.execute('''
    CREATE TABLE IF NOT EXISTS invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer TEXT NOT NULL,
        product TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        total REAL NOT NULL,
        date TEXT NOT NULL
    )
''')
conn.commit()
cur.execute('DELETE FROM invoices')
cur.execute('DELETE FROM sqlite_sequence WHERE name = "invoices"')
conn.commit()
conn.close()
print('Database cleared and ID reset to 1')

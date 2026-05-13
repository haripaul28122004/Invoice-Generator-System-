#!/usr/bin/env python
"""
Script to create a test employee user with plain text password
"""
import sqlite3
from datetime import datetime

DATABASE = 'database.db'

def create_test_user():
    """Create test employee user"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    email = 'haripaul28122004@gmail.com'
    password = 'haripaul007'
    username = 'Hari Paul'
    role = 'user'
    
    try:
        # Check if user already exists
        existing = cur.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing:
            print(f"✓ User {email} already exists with role '{existing['role']}'")
            return
        
        # Insert user with plain text password
        cur.execute(
            'INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
            (username, email, password, role)
        )
        conn.commit()
        print(f"✅ Test user created successfully!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: {role}")
        print(f"   Username: {username}")
        
    except Exception as e:
        print(f"❌ Error creating user: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    create_test_user()

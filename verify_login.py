#!/usr/bin/env python
"""
Script to verify user login authentication works with plain text passwords
"""
import sqlite3

DATABASE = 'database.db'

def verify_user_auth():
    """Verify user authentication"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    email = 'haripaul28122004@gmail.com'
    password = 'haripaul007'
    
    print("Testing User Login Authentication\n")
    print(f"Email: {email}")
    print(f"Password: {password}\n")
    
    # Fetch user
    user = cur.execute('SELECT * FROM users WHERE email = ? AND role = ?', (email, 'user')).fetchone()
    
    if not user:
        print("❌ User not found in database!")
        print("   Please run: python create_test_user.py")
        conn.close()
        return False
    
    print(f"✓ User found: {user['username']}")
    print(f"✓ Stored password: {user['password']}")
    print(f"✓ Role: {user['role']}")
    
    # Test password comparison
    if user['password'] == password:
        print("\n✅ Password verification PASSED!")
        print("   Login will succeed with:")
        print(f"   - Plain text password comparison: user['password'] == password")
        conn.close()
        return True
    else:
        print("\n❌ Password verification FAILED!")
        print(f"   Expected: {password}")
        print(f"   Got: {user['password']}")
        conn.close()
        return False

if __name__ == '__main__':
    verify_user_auth()

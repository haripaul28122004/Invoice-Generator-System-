#!/usr/bin/env python
"""
Test script for Invoice Management System
- Verify database schema
- Test email configuration
- Test invoice creation flow
"""
import sqlite3
from datetime import datetime

DATABASE = 'database.db'

def test_database_schema():
    """Verify database tables and columns"""
    print("\n=== Database Schema Verification ===\n")
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Check users table
    print("✓ Checking 'users' table structure...")
    cur.execute("PRAGMA table_info(users)")
    users_cols = cur.fetchall()
    print("  Columns:")
    for col in users_cols:
        print(f"    - {col[1]} ({col[2]}) NULL:{col[3]}")
    
    # Verify email column
    email_col = [col for col in users_cols if col[1] == 'email']
    if email_col and email_col[0][3] == 0:  # NOT NULL
        print("  ✓ Email column is NOT NULL")
    else:
        print("  ✗ Email column is NULL - this could be a problem!")
    
    # Check for UNIQUE constraint on email
    cur.execute("PRAGMA index_list(users)")
    indexes = cur.fetchall()
    has_email_unique = any('email' in str(idx) for idx in indexes)
    if has_email_unique:
        print("  ✓ Email has UNIQUE constraint")
    else:
        print("  ⚠ Email UNIQUE constraint status unclear")
    
    # Check invoices table
    print("\n✓ Checking 'invoices' table structure...")
    cur.execute("PRAGMA table_info(invoices)")
    invoices_cols = cur.fetchall()
    print("  Columns:")
    for col in invoices_cols:
        print(f"    - {col[1]} ({col[2]})")
    
    conn.close()
    print()

def test_employee_data():
    """Verify employee data is available"""
    print("=== Employee Data Verification ===\n")
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all employees
    cur.execute("SELECT username, email, role FROM users WHERE role = 'user' ORDER BY username")
    employees = cur.fetchall()
    
    if employees:
        print(f"✓ Found {len(employees)} employee(s):\n")
        for emp in employees:
            print(f"  - {emp['username']:20} | {emp['email']:30} | Role: {emp['role']}")
    else:
        print("✗ No employees found in database!")
        print("  Run: python create_test_user.py")
    
    conn.close()
    print()

def test_products_data():
    """Verify products are available"""
    print("=== Products Data Verification ===\n")
    
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Get all products
    cur.execute("SELECT id, name, category, price, gst, stock FROM products ORDER BY category, name")
    products = cur.fetchall()
    
    if products:
        print(f"✓ Found {len(products)} product(s):\n")
        print(f"  {'ID':<3} {'Name':<20} {'Category':<15} {'Price':<10} {'GST':<6} {'Stock':<6}")
        print("  " + "-" * 60)
        for prod in products:
            print(f"  {prod['id']:<3} {prod['name']:<20} {prod['category']:<15} ₹{prod['price']:<9.2f} {prod['gst']*100:<5.0f}% {prod['stock']:<6}")
    else:
        print("✗ No products found in database!")
        print("  Run: /seed_data route or python reset_and_seed_db.py")
    
    conn.close()
    print()

def test_email_config():
    """Check email configuration"""
    print("=== Email Configuration Check ===\n")
    
    try:
        from app import app, mail
        
        print("✓ Flask-Mail is installed")
        
        config = {
            'MAIL_SERVER': app.config.get('MAIL_SERVER'),
            'MAIL_PORT': app.config.get('MAIL_PORT'),
            'MAIL_USE_TLS': app.config.get('MAIL_USE_TLS'),
            'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
            'MAIL_PASSWORD': '***' if app.config.get('MAIL_PASSWORD') else None,
        }
        
        print("\nConfiguration:")
        for key, value in config.items():
            print(f"  {key}: {value}")
        
        # Check if defaults are still set
        if 'your_email@gmail.com' in str(app.config.get('MAIL_USERNAME', '')):
            print("\n⚠ WARNING: Email configuration not updated!")
            print("  Update app.py with your actual Gmail or email service credentials")
        elif app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD'):
            print("\n✓ Email configuration appears to be set")
        
    except ImportError:
        print("✗ Flask-Mail is NOT installed")
        print("  Run: pip install Flask-Mail")
    
    print()

def test_invoice_flow():
    """Test invoice creation flow (database only, no email)"""
    print("=== Invoice Creation Flow Test ===\n")
    
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Get a test employee
        cur.execute("SELECT username, email FROM users WHERE role = 'user' LIMIT 1")
        employee = cur.fetchone()
        
        if not employee:
            print("✗ No employees found - cannot test invoice creation")
            conn.close()
            return
        
        # Get a test product
        cur.execute("SELECT id, name, price, gst, stock FROM products LIMIT 1")
        product = cur.fetchone()
        
        if not product:
            print("✗ No products found - cannot test invoice creation")
            conn.close()
            return
        
        print(f"Test Data:")
        print(f"  Employee: {employee['username']} ({employee['email']})")
        print(f"  Product: {product['name']} (₹{product['price']:.2f}, Stock: {product['stock']})")
        
        if product['stock'] <= 0:
            print(f"\n⚠ Product has no stock - invoice creation would fail")
        else:
            print(f"\n✓ Test data is valid for invoice creation")
        
        conn.close()
        
    except Exception as e:
        print(f"✗ Error during flow test: {str(e)}")
    
    print()

def main():
    print("\n" + "="*60)
    print("INVOICE MANAGEMENT SYSTEM - TEST SUITE")
    print("="*60)
    
    test_database_schema()
    test_employee_data()
    test_products_data()
    test_email_config()
    test_invoice_flow()
    
    print("="*60)
    print("TEST COMPLETE")
    print("="*60)
    print("\nNext Steps:")
    print("1. Configure email in app.py (EMAIL_SETUP_GUIDE.md)")
    print("2. Run Flask app: python app.py")
    print("3. Visit http://localhost:5000/user_login")
    print("4. Login with: haripaul28122004@gmail.com / haripaul007")
    print("5. Create an invoice from the employee portal")
    print()

if __name__ == '__main__':
    main()

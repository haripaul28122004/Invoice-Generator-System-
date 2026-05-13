#!/usr/bin/env python
"""
Check and reset database schema
"""
import sqlite3
import os
from datetime import datetime

DATABASE = 'database.db'

def check_and_reset_db():
    """Check database schema and reset if needed"""
    
    # Delete existing database
    if os.path.exists(DATABASE):
        os.remove(DATABASE)
        print("✓ Deleted old database.db")
    
    # Create fresh database
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    print("Creating fresh database schema...")
    
    # Create users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    ''')
    
    # Create products table with NEW schema (includes category and stock)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT DEFAULT 'General',
            price REAL NOT NULL,
            gst REAL NOT NULL DEFAULT 0.18,
            stock INTEGER DEFAULT 0,
            created_date TEXT NOT NULL
        )
    ''')
    
    # Create chatbot_training table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chatbot_training (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT
        )
    ''')
    
    # Create invoices table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER,
            product_id INTEGER,
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            total REAL NOT NULL,
            date TEXT NOT NULL,
            created_by TEXT,
            FOREIGN KEY (customer_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    ''')
    
    conn.commit()
    print("✓ Database schema created successfully\n")
    
    # Verify schema
    cur.execute("PRAGMA table_info(products)")
    columns = cur.fetchall()
    print("📋 Products table schema:")
    for col in columns:
        print(f"   - {col[1]} ({col[2]})")
    
    # Now seed sample data
    print("\n🌱 Seeding sample products...")
    
    sample_products = [
        ('Laptop', 'Electronics', 50000, 0.18, 10),
        ('Mobile Phone', 'Electronics', 20000, 0.18, 15),
        ('Office Chair', 'Furniture', 1500, 0.12, 25),
        ('Office Table', 'Furniture', 3000, 0.12, 10),
        ('Pizza', 'Food', 200, 0.05, 50),
        ('Coffee', 'Beverages', 100, 0.05, 100),
        ('Monitor', 'Electronics', 15000, 0.18, 8),
        ('Keyboard', 'Electronics', 2000, 0.18, 30),
    ]
    
    for name, category, price, gst, stock in sample_products:
        cur.execute(
            'INSERT INTO products (name, category, price, gst, stock, created_date) VALUES (?, ?, ?, ?, ?, ?)',
            (name, category, price, gst, stock, datetime.now().strftime('%d-%m-%Y'))
        )
    
    conn.commit()
    print(f"✓ Successfully created {len(sample_products)} sample products\n")
    
    # Display inserted products
    print("📦 Inserted Products:")
    products = cur.execute('SELECT * FROM products ORDER BY category, name').fetchall()
    for p in products:
        print(f"   - {p['name']:20} ({p['category']:12}) | ₹{p['price']:7.0f} | Stock: {p['stock']:3} | GST: {p['gst']*100:.0f}%")
    
    conn.close()
    print("\n✅ Database initialization complete!")

if __name__ == '__main__':
    check_and_reset_db()

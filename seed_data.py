#!/usr/bin/env python
"""
Script to initialize sample products into the database
"""
import sqlite3
from datetime import datetime

DATABASE = 'database.db'

def seed_products():
    """Initialize sample products"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Check if products already exist
    existing = cur.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
    
    if existing == 0:
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
        print(f"✅ Successfully created {len(sample_products)} sample products")
        
        # Display inserted products
        print("\n📦 Inserted Products:")
        products = cur.execute('SELECT * FROM products ORDER BY category, name').fetchall()
        for p in products:
            print(f"  - {p['name']} ({p['category']}) | ₹{p['price']} | Stock: {p['stock']}")
    else:
        print(f"ℹ️  Database already has {existing} products. Skipping seed.")
        
        # Display existing products
        products = cur.execute('SELECT * FROM products ORDER BY category, name').fetchall()
        print("\n📦 Existing Products:")
        for p in products:
            print(f"  - {p['name']} ({p['category']}) | ₹{p['price']} | Stock: {p['stock']}")
    
    conn.close()

if __name__ == '__main__':
    seed_products()

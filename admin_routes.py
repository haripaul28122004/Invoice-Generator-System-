from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import json
from datetime import datetime
from werkzeug.security import generate_password_hash

# Import necessary helpers from app (will be resolved when registered)
import app

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin_dashboard')
@app.require_role('admin')
def admin_dashboard():
    conn = app.get_db_connection()
    
    # Get statistics
    totals = conn.execute('SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS revenue FROM invoices').fetchone()
    customer_count = conn.execute('SELECT COUNT(DISTINCT customer) AS count FROM invoices').fetchone()['count']
    invoice_count = totals['count']
    total_revenue = totals['revenue']
    
    # Get AI insights
    ai_insights = app.get_ai_insights(conn)
    
    # Get chart data
    sales_chart = app.get_sales_chart_data(conn)
    product_qty_chart = app.get_product_quantity_data(conn)
    revenue_dist_chart = app.get_revenue_distribution_data(conn)
    
    # AI revenue prediction (RandomForest)
    ai_revenue = app.predict_revenue(app.DATABASE)
    best_product = app.predict_best_product(app.DATABASE)

    # Growth %: predicted vs current total
    growth_pct = None
    if total_revenue and ai_revenue['predicted']:
        growth_pct = round(
            ((ai_revenue['predicted'] - total_revenue) / total_revenue) * 100, 1
        )


    # Fetch all invoices for the admin table
    invoices = conn.execute('SELECT * FROM invoices ORDER BY id DESC').fetchall()

    conn.close()

    return render_template(
        'admin/dashboard.html',
        invoice_count=invoice_count,
        total_revenue=total_revenue,
        customer_count=customer_count,
        ai_insights=ai_insights,
        ai_revenue=ai_revenue,
        best_product=best_product,
        growth_pct=growth_pct,
        sales_chart_data=json.dumps(sales_chart),
        product_qty_chart_data=json.dumps(product_qty_chart),
        revenue_dist_chart_data=json.dumps(revenue_dist_chart),
        invoices=invoices
    )


@admin_bp.route('/admin/customers')
@app.require_role('admin')
def admin_customers():
    conn = app.get_db_connection()
    customers = conn.execute('''
        SELECT customer, COUNT(*) as invoice_count, SUM(total) as total_spent
        FROM invoices
        GROUP BY customer
        ORDER BY total_spent DESC
    ''').fetchall()
    conn.close()
    return render_template('admin/customers.html', customers=customers)


@admin_bp.route('/admin/products', methods=['GET', 'POST'])
@app.require_role('admin')
def admin_products():
    conn = app.get_db_connection()
    
    if request.method == 'POST':
        product_name = request.form.get('product_name', '').strip()
        product_category = request.form.get('product_category', 'General').strip()
        product_price = request.form.get('product_price', '').strip()
        product_gst = request.form.get('product_gst', '0.18').strip()
        product_stock = request.form.get('product_stock', '0').strip()

        try:
            if not product_name:
                raise ValueError('Product name is required.')
            if not product_price:
                raise ValueError('Product price is required.')
            
            product_price = float(product_price)
            if product_price <= 0:
                raise ValueError('Price must be greater than zero.')
            
            product_gst = float(product_gst)
            if product_gst < 0 or product_gst > 1:
                raise ValueError('GST must be between 0 and 1 (0-100%).')
            
            product_stock = int(product_stock)
            if product_stock < 0:
                raise ValueError('Stock cannot be negative.')

            conn.execute(
                'INSERT INTO products (name, category, price, gst, stock, created_date) VALUES (?, ?, ?, ?, ?, ?)',
                (product_name, product_category, product_price, product_gst, product_stock, datetime.now().strftime('%d-%m-%Y'))
            )
            conn.commit()
            flash('Product added successfully.', 'success')
            return redirect(url_for('admin.admin_products'))

        except ValueError as error:
            flash(str(error), 'danger')
        except sqlite3.IntegrityError:
            flash('Product with this name already exists.', 'warning')
        except Exception as e:
            flash(f'Error adding product: {str(e)}', 'danger')

    products = conn.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
    conn.close()

    return render_template('admin/products.html', products=products)


@admin_bp.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@app.require_role('admin')
def delete_product(product_id):
    conn = app.get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('admin.admin_products'))


@admin_bp.route('/admin/invoices/<int:invoice_id>/delete', methods=['POST'])
@app.require_role('admin')
def admin_delete_invoice(invoice_id):
    conn = app.get_db_connection()
    conn.execute('DELETE FROM invoices WHERE id = ?', (invoice_id,))
    conn.commit()
    conn.close()
    flash(f'Invoice #{invoice_id} deleted successfully.', 'success')
    return redirect(url_for('admin.admin_dashboard'))


@admin_bp.route('/admin/employees', methods=['GET', 'POST'])
@app.require_role('admin')
def admin_employees():
    conn = app.get_db_connection()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not username:
            flash('Username is required.', 'danger')
        elif not email or '@' not in email:
            flash('A valid email address is required.', 'danger')
        elif not password:
            flash('Password cannot be empty.', 'danger')
        else:
            try:
                existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
                if existing:
                    flash(f'An account with email "{email}" already exists.', 'warning')
                else:
                    hashed = generate_password_hash(password)
                    conn.execute(
                        'INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                        (username, email, hashed, 'user')
                    )
                    conn.commit()
                    flash(f'Employee "{username}" added successfully.', 'success')
            except Exception as e:
                flash(f'Error creating employee: {str(e)}', 'danger')
        
        conn.close()
        return redirect(url_for('admin.admin_employees'))
    
    # GET request: fetch employees
    employees = conn.execute(
        "SELECT id, username, email FROM users WHERE role = 'user' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    
    return render_template('admin/employees.html', employees=employees)


@admin_bp.route('/admin/delete_employee/<int:employee_id>', methods=['POST'])
@app.require_role('admin')
def admin_delete_employee(employee_id):
    PROTECTED_EMAIL = 'haripaul282004@gmail.com'
    try:
        conn = app.get_db_connection()
        target = conn.execute('SELECT email FROM users WHERE id = ? AND role = ?', (employee_id, 'user')).fetchone()
        if not target:
            conn.close()
            flash('Employee not found.', 'warning')
            return redirect(url_for('admin.admin_employees'))
        if target['email'] == PROTECTED_EMAIL:
            conn.close()
            flash('The default employee account cannot be deleted.', 'warning')
            return redirect(url_for('admin.admin_employees'))
        conn.execute('DELETE FROM users WHERE id = ?', (employee_id,))
        conn.commit()
        conn.close()
        flash('Employee deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting employee: {str(e)}', 'danger')
    return redirect(url_for('admin.admin_employees'))


@admin_bp.route('/train_chatbot', methods=['POST'])
@app.require_role('admin')
def train_chatbot():
    try:
        question = request.form.get('question', '').strip().lower()
        answer = request.form.get('answer', '').strip()
        
        if not question or not answer:
            flash('Both question and answer are required.', 'warning')
            return redirect(url_for('admin.admin_dashboard'))
        
        conn = app.get_db_connection()
        existing = conn.execute("SELECT id FROM chatbot_training WHERE question=?", (question,)).fetchone()
        
        if existing:
            conn.execute("UPDATE chatbot_training SET answer=? WHERE question=?", (answer, question))
            flash('Chatbot training updated successfully.', 'success')
        else:
            conn.execute("INSERT INTO chatbot_training (question, answer) VALUES (?, ?)", (question, answer))
            flash('Chatbot training added successfully.', 'success')
        
        conn.commit()
        conn.close()
        return redirect(url_for('admin.admin_dashboard'))
    except Exception as e:
        flash(f'Error training chatbot: {str(e)}', 'danger')
        return redirect(url_for('admin.admin_dashboard'))


# ============================================


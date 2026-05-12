from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
import io
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from functools import wraps

app = Flask(__name__)
app.secret_key = 'invoice_flow_secret_key_2026'
DATABASE = 'database.db'
ADMIN_EMAIL = 'haripaul28122004@gmail.com'
ADMIN_PASSWORD = 'haripaul007'


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL,
            created_date TEXT NOT NULL
        )
    ''')
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
    conn.close()


# Role-based access control decorators
def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            if not user_role or user_role not in roles:
                flash(f'Access denied. Required role: {", ".join(roles)}', 'danger')
                if user_role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user_role == 'user':
                    return redirect(url_for('user_dashboard'))
                elif user_role == 'customer':
                    return redirect(url_for('customer_dashboard'))
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/')
def home():
    if session.get('username'):
        return redirect(url_for('dashboard'))
    return render_template('index.html')


# ============================================
# ADMIN ROUTES
# ============================================

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if email != ADMIN_EMAIL or password != ADMIN_PASSWORD:
            flash('Invalid admin credentials. Please try again.', 'danger')
            return render_template('admin/login.html')

        session['username'] = email
        session['role'] = 'admin'
        session['user_id'] = 0
        flash('Admin logged in successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/login.html')


@app.route('/admin_dashboard')
@require_role('admin')
def admin_dashboard():
    conn = get_db_connection()
    
    # Get statistics
    totals = conn.execute('SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS revenue FROM invoices').fetchone()
    customer_count = conn.execute('SELECT COUNT(DISTINCT customer) AS count FROM invoices').fetchone()['count']
    invoice_count = totals['count']
    total_revenue = totals['revenue']
    
    # Get recent invoices
    recent_invoices = conn.execute('SELECT * FROM invoices ORDER BY id DESC LIMIT 10').fetchall()
    conn.close()

    return render_template(
        'admin/dashboard.html',
        invoice_count=invoice_count,
        total_revenue=total_revenue,
        customer_count=customer_count,
        recent_invoices=recent_invoices
    )


@app.route('/admin/customers')
@require_role('admin')
def admin_customers():
    conn = get_db_connection()
    
    # Get distinct customers from invoices
    customers = conn.execute('''
        SELECT DISTINCT customer, COUNT(*) as invoice_count, SUM(total) as total_spent
        FROM invoices
        GROUP BY customer
        ORDER BY total_spent DESC
    ''').fetchall()
    conn.close()

    return render_template('admin/customers.html', customers=customers)


@app.route('/admin/products', methods=['GET', 'POST'])
@require_role('admin')
def admin_products():
    conn = get_db_connection()
    
    if request.method == 'POST':
        product_name = request.form.get('product_name', '').strip()
        product_price = request.form.get('product_price', '').strip()

        try:
            if not product_name or not product_price:
                raise ValueError('Product name and price are required.')
            
            product_price = float(product_price)
            if product_price < 0:
                raise ValueError('Price cannot be negative.')

            conn.execute(
                'INSERT INTO products (name, price, created_date) VALUES (?, ?, ?)',
                (product_name, product_price, datetime.now().strftime('%d-%m-%Y'))
            )
            conn.commit()
            flash('Product added successfully.', 'success')
            return redirect(url_for('admin_products'))

        except ValueError as error:
            flash(str(error), 'danger')
        except sqlite3.IntegrityError:
            flash('Product with this name already exists.', 'warning')
        except Exception as e:
            flash(f'Error adding product: {str(e)}', 'danger')

    products = conn.execute('SELECT * FROM products ORDER BY id DESC').fetchall()
    conn.close()

    return render_template('admin/products.html', products=products)


@app.route('/admin/products/<int:product_id>/delete', methods=['POST'])
@require_role('admin')
def delete_product(product_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('admin_products'))


@app.route('/admin/create_invoice', methods=['GET', 'POST'])
@require_role('admin')
def admin_create_invoice():
    conn = get_db_connection()
    
    if request.method == 'POST':
        customer = request.form.get('customer', '').strip()
        product = request.form.get('product', '').strip()
        quantity = request.form.get('quantity', '').strip()
        price = request.form.get('price', '').strip()

        try:
            if not customer or not product:
                raise ValueError('Customer and product are required.')

            quantity = int(quantity)
            price = float(price)

            if quantity <= 0 or price < 0:
                raise ValueError('Quantity must be greater than zero and price cannot be negative.')

            total = round(quantity * price, 2)
            date = datetime.now().strftime('%d-%m-%Y')

            conn.execute(
                'INSERT INTO invoices (customer, product, quantity, price, total, date, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (customer, product, quantity, price, total, date, session.get('username'))
            )
            conn.commit()
            flash('Invoice created successfully.', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception:
            flash('Unable to save invoice. Please verify your data.', 'danger')

    products = conn.execute('SELECT * FROM products ORDER BY name').fetchall()
    conn.close()
    return render_template('admin/create_invoice.html', products=products)


@app.route('/admin/invoices/<int:invoice_id>/delete', methods=['POST'])
@require_role('admin')
def admin_delete_invoice(invoice_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM invoices WHERE id = ?', (invoice_id,))
    conn.commit()
    conn.close()
    flash(f'Invoice #{invoice_id} deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


# ============================================
# USER (EMPLOYEE) ROUTES
# ============================================

@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND role = ?', (email, 'user')).fetchone()
        conn.close()

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('user/login.html')

        session['username'] = user['username']
        session['email'] = user['email']
        session['user_id'] = user['id']
        session['role'] = 'user'
        flash('User logged in successfully.', 'success')
        return redirect(url_for('user_dashboard'))

    if session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))

    return render_template('user/login.html')


@app.route('/user_dashboard')
@require_role('user')
def user_dashboard():
    conn = get_db_connection()
    
    invoices = conn.execute('SELECT * FROM invoices ORDER BY id DESC').fetchall()
    totals = conn.execute('SELECT COALESCE(SUM(total), 0) AS revenue FROM invoices').fetchone()
    total_revenue = totals['revenue'] if totals else 0
    
    conn.close()

    return render_template('user/dashboard.html', invoices=invoices, total_revenue=total_revenue)


@app.route('/create_invoice', methods=['GET', 'POST'])
@require_role('user')
def create_invoice():
    conn = get_db_connection()
    
    if request.method == 'POST':
        customer = request.form.get('customer', '').strip()
        product_id = request.form.get('product_id', '').strip()
        quantity = request.form.get('quantity', '').strip()

        try:
            if not customer or not product_id:
                raise ValueError('Customer and product are required.')

            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError('Quantity must be greater than zero.')

            # Get product details
            product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            if not product:
                raise ValueError('Product not found.')

            price = product['price']
            product_name = product['name']
            total = round(quantity * price, 2)
            date = datetime.now().strftime('%d-%m-%Y')

            conn.execute(
                'INSERT INTO invoices (customer, product, quantity, price, total, date, created_by, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (customer, product_name, quantity, price, total, date, session.get('username'), product_id)
            )
            conn.commit()
            flash('Invoice created successfully.', 'success')
            return redirect(url_for('user_dashboard'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception as e:
            flash(f'Error creating invoice: {str(e)}', 'danger')

    products = conn.execute('SELECT * FROM products ORDER BY name').fetchall()
    conn.close()
    
    return render_template('user/create_invoice.html', products=products)


@app.route('/user/customers')
@require_role('user')
def user_customers():
    conn = get_db_connection()
    
    customers = conn.execute('''
        SELECT DISTINCT customer, COUNT(*) as invoice_count, SUM(total) as total_spent
        FROM invoices
        GROUP BY customer
        ORDER BY customer ASC
    ''').fetchall()
    conn.close()

    return render_template('user/customers.html', customers=customers)


# ============================================
# CUSTOMER ROUTES
# ============================================

@app.route('/customer_login', methods=['GET', 'POST'])
def customer_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND role = ?', (email, 'customer')).fetchone()
        conn.close()

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('customer/login.html')

        session['username'] = user['username']
        session['email'] = user['email']
        session['user_id'] = user['id']
        session['role'] = 'customer'
        flash('Customer logged in successfully.', 'success')
        return redirect(url_for('customer_dashboard'))

    if session.get('role') == 'customer':
        return redirect(url_for('customer_dashboard'))

    return render_template('customer/login.html')


@app.route('/customer_register', methods=['GET', 'POST'])
def customer_register():
    if session.get('role') == 'customer':
        return redirect(url_for('customer_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        try:
            if not username or not email or not password or not confirm_password:
                raise ValueError('All fields are required.')
            if password != confirm_password:
                raise ValueError('Passwords do not match.')
            if len(password) < 6:
                raise ValueError('Password must be at least 6 characters long.')

            conn = get_db_connection()
            existing = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if existing:
                raise ValueError('A user with that email already exists.')

            conn.execute(
                'INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)',
                (username, email, generate_password_hash(password), 'customer')
            )
            conn.commit()
            conn.close()

            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('customer_login'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception:
            flash('Unable to complete registration. Please try again.', 'danger')

    return render_template('customer/register.html')


@app.route('/customer_dashboard')
@require_role('customer')
def customer_dashboard():
    conn = get_db_connection()
    
    # Get invoices where customer name matches the logged-in customer
    invoices = conn.execute('SELECT * FROM invoices WHERE customer = ? ORDER BY id DESC', (session.get('username'),)).fetchall()
    totals = conn.execute('SELECT COALESCE(SUM(total), 0) AS revenue FROM invoices WHERE customer = ?', (session.get('username'),)).fetchone()
    total_revenue = totals['revenue'] if totals else 0
    
    conn.close()

    return render_template('customer/dashboard.html', invoices=invoices, total_revenue=total_revenue)


@app.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    if not session.get('username'):
        return redirect(url_for('home'))

    conn = get_db_connection()
    invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
    conn.close()

    if invoice is None:
        flash('Invoice not found.', 'warning')
        return redirect(url_for('dashboard'))

    # Access control for customers
    if session.get('role') == 'customer' and invoice['customer'] != session.get('username'):
        flash('You do not have access to this invoice.', 'danger')
        return redirect(url_for('customer_dashboard'))

    return render_template('invoice.html', invoice=invoice)


@app.route('/invoice/<int:invoice_id>/download')
def download_invoice(invoice_id):
    if not session.get('username'):
        return redirect(url_for('home'))

    conn = get_db_connection()
    invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
    conn.close()

    if invoice is None:
        flash('Invoice not found.', 'warning')
        return redirect(url_for('dashboard'))

    # Access control for customers
    if session.get('role') == 'customer' and invoice['customer'] != session.get('username'):
        flash('You do not have access to this invoice.', 'danger')
        return redirect(url_for('customer_dashboard'))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=32, leftMargin=32, topMargin=32, bottomMargin=32)
    styles = getSampleStyleSheet()
    elements = []

    title_style = styles['Title']
    title_style.alignment = 1
    elements.append(Paragraph('Invoice', title_style))
    elements.append(Spacer(1, 18))

    header_data = [
        ['Invoice ID:', str(invoice['id'])],
        ['Date:', invoice['date']],
        ['Customer:', invoice['customer']]
    ]
    header_table = Table(header_data, colWidths=[100, 340])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#334155')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica')
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 24))

    invoice_table = Table([
        ['Product / Service', 'Quantity', 'Unit Price', 'Total'],
        [invoice['product'], str(invoice['quantity']), f"Rs. {invoice['price']:.2f}", f"Rs. {invoice['total']:.2f}"]
    ], colWidths=[220, 90, 100, 120])
    invoice_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4f46e5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d6d6d6')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.whitesmoke)
    ]))
    elements.append(invoice_table)
    elements.append(Spacer(1, 24))

    summary_data = [['Grand Total', f"Rs. {invoice['total']:.2f}"]]
    summary_table = Table(summary_data, colWidths=[320, 210])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1f2937')),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12)
    ]))
    elements.append(summary_table)

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=f"invoice_{invoice['id']}.pdf")


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    if not session.get('username'):
        return redirect(url_for('home'))

    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))
    elif session.get('role') == 'customer':
        return redirect(url_for('customer_dashboard'))
    
    return redirect(url_for('home'))


if __name__ == '__main__':
    init_db()
    print(app.url_map)
    app.run(debug=True, use_reloader=False)




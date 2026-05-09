from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import sqlite3
import io
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet

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
    conn.close()


@app.route('/')
def home():
    if session.get('username'):
        return redirect(url_for('dashboard'))
    return render_template('index.html')


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
        flash('Admin logged in successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))
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
                (username, email, generate_password_hash(password), 'user')
            )
            conn.commit()
            conn.close()

            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('user_login'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception:
            flash('Unable to complete registration. Please try again.', 'danger')

    return render_template('user/register.html')


@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()

        if not user or not check_password_hash(user['password'], password):
            flash('Invalid email or password. Please try again.', 'danger')
            return render_template('user/login.html')

        session['username'] = user['username']
        session['email'] = user['email']
        session['role'] = 'user'
        flash('User logged in successfully.', 'success')
        return redirect(url_for('user_dashboard'))

    if session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))

    return render_template('user/login.html')


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
    return redirect(url_for('user_dashboard'))

@app.route('/reset_invoices', methods=['POST'])
def reset_invoices():
    if session.get('role') != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('admin_login'))

    import sqlite3

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("DELETE FROM invoices")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='invoices'")

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    invoices = conn.execute('SELECT * FROM invoices ORDER BY id DESC').fetchall()
    totals = conn.execute('SELECT COUNT(*) AS count, COALESCE(SUM(total), 0) AS revenue FROM invoices').fetchone()
    user_count = conn.execute('SELECT COUNT(*) AS count FROM users').fetchone()['count']
    conn.close()

    return render_template(
        'admin/dashboard.html',
        invoices=invoices,
        invoice_count=totals['count'],
        total_revenue=totals['revenue'],
        user_count=user_count
    )


@app.route('/users', endpoint='view_users')
def view_users():
    if session.get('role') != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('admin_login'))

    import sqlite3

    conn = sqlite3.connect('database.db')
    cur = conn.cursor()

    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    conn.close()

    return render_template('admin/users.html', users=users)


@app.route('/admin_create', methods=['GET', 'POST'])
def admin_create():
    if session.get('role') != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('admin_login'))

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

            conn = get_db_connection()
            conn.execute(
                'INSERT INTO invoices (customer, product, quantity, price, total, date) VALUES (?, ?, ?, ?, ?, ?)',
                (customer, product, quantity, price, total, date)
            )
            conn.commit()
            conn.close()

            flash('Invoice created successfully.', 'success')
            return redirect(url_for('admin_dashboard'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception:
            flash('Unable to save invoice. Please verify your data.', 'danger')

    return render_template('admin/create_invoice.html')


@app.route('/user_dashboard')
def user_dashboard():
    if session.get('role') != 'user':
        flash('User access required.', 'danger')
        return redirect(url_for('user_login'))

    conn = get_db_connection()
    invoices = conn.execute('SELECT * FROM invoices ORDER BY id DESC').fetchall()
    totals = conn.execute('SELECT COALESCE(SUM(total), 0) AS revenue FROM invoices').fetchone()
    conn.close()

    total_revenue = totals['revenue'] if totals else 0

    return render_template('user/dashboard.html', invoices=invoices, total_revenue=total_revenue)


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

    return render_template('user/invoice.html', invoice=invoice)


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
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4b6cb7')),
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


@app.route('/delete/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    if session.get('role') != 'admin':
        flash('Admin access required.', 'danger')
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    conn.execute('DELETE FROM invoices WHERE id = ?', (invoice_id,))
    conn.commit()
    conn.close()

    flash(f'Invoice #{invoice_id} deleted successfully.', 'success')
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    init_db()
    print(app.url_map)
    app.run(debug=True, use_reloader=False)

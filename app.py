from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
import sqlite3
import io
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from functools import wraps
import json

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
            gst REAL NOT NULL DEFAULT 0.18,
            created_date TEXT NOT NULL
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS chatbot_training (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT
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


# ============================================
# AI & ANALYTICS HELPER FUNCTIONS
# ============================================

def calculate_tax(subtotal, gst_rate=0.18):
    """Calculate tax on subtotal with dynamic GST rate"""
    tax = round(subtotal * gst_rate, 2)
    final_total = round(subtotal + tax, 2)
    return {"tax": tax, "final_total": final_total, "gst_rate": gst_rate}


def get_product_gst(conn, product_name):
    """Get GST rate for a product from database"""
    try:
        result = conn.execute("SELECT gst FROM products WHERE name=?", (product_name,)).fetchone()
        if result is not None:
            return result[0]
    except:
        pass
    return 0.18  # Default GST rate


def ai_chatbot_query(query):
    """Trainable AI chatbot with database learning"""
    query_lower = query.lower().strip()
    
    try:
        conn = get_db_connection()
        
        # Check trained responses first
        result = conn.execute(
            "SELECT answer FROM chatbot_training WHERE question LIKE ?", 
            ('%' + query_lower + '%',)
        ).fetchone()
        
        if result and result[0]:
            conn.close()
            return result[0]
        
        # Smart fallback responses
        if any(word in query_lower for word in ['invoice', 'create']):
            response = "📋 To create an invoice, navigate to 'Create Invoice' from the menu. Fill in customer name, select a product, and enter quantity. The system will automatically calculate tax and total for you!"
        elif any(word in query_lower for word in ['customer', 'customers']):
            response = "👥 Customers are available in the 'Customers' section of your dashboard. You can view all customers, their purchase history, and total spending."
        elif any(word in query_lower for word in ['download', 'pdf', 'export']):
            response = "📥 To download an invoice as PDF: Go to 'My Invoices' → Click on the invoice → Click 'Download as PDF'."
        elif any(word in query_lower for word in ['product', 'products', 'add']):
            response = "📦 Products are managed in the 'Products' section (Admin only). Add new products with name, price, and GST rate. Products can be selected when creating invoices."
        elif any(word in query_lower for word in ['login', 'password']):
            response = "🔐 Use your registered email and password to login. If you forgot your password, contact the admin."
        elif any(word in query_lower for word in ['dashboard', 'report', 'analytics', 'chart']):
            response = "📊 Your dashboard shows summary cards with key metrics, AI insights, and charts. Line chart shows sales over time, bar chart shows product sales, and pie chart shows revenue distribution."
        elif any(word in query_lower for word in ['tax', 'gst']):
            response = "💰 The system automatically calculates GST on all invoices based on product settings. GST is added to the subtotal to calculate the final total."
        elif any(word in query_lower for word in ['help', 'support']):
            response = "❓ I'm here to help! Ask me about: invoices, customers, products, downloads, charts, GST, or any other features."
        else:
            response = "🤔 I'm not sure about that. Try asking about: invoices, customers, products, downloads, charts, or contact your admin for more help."
            # Log unanswered questions for admin training
            conn.execute(
                "INSERT OR IGNORE INTO chatbot_training (question, answer) VALUES (?, ?)",
                (query_lower, "")
            )
            conn.commit()
        
        conn.close()
        return response
    except:
        return "⚠️ I'm having trouble connecting. Please try again."


def generate_email(customer, product, total, invoice_id):
    """Generate email template for invoice"""
    email_content = f"""
Dear {customer},

Thank you for your purchase!

Invoice Details:
- Invoice ID: {invoice_id}
- Product: {product}
- Total Amount: ₹{total:.2f}

Please keep this for your records.

Best regards,
Invoice Management Team
    """.strip()
    return email_content


def get_revenue_prediction(conn):
    """Predict next month revenue based on average daily revenue"""
    try:
        invoices = conn.execute('SELECT total, date FROM invoices ORDER BY date DESC LIMIT 30').fetchall()
        
        if len(invoices) == 0:
            return None
        
        total_revenue = sum(inv['total'] for inv in invoices)
        avg_daily = total_revenue / 30
        predicted_monthly = round(avg_daily * 30, 2)
        
        return predicted_monthly
    except:
        return None


def get_top_product(conn):
    """Get most sold product"""
    try:
        top = conn.execute('''
            SELECT product, SUM(quantity) as total_qty, SUM(total) as revenue
            FROM invoices
            GROUP BY product
            ORDER BY total_qty DESC
            LIMIT 1
        ''').fetchone()
        
        if top:
            return {
                "name": top['product'],
                "quantity": top['total_qty'],
                "revenue": round(top['revenue'], 2)
            }
        return None
    except:
        return None


def get_low_sales_alert(conn):
    """Detect products with low quantity"""
    try:
        low_products = conn.execute('''
            SELECT product, SUM(quantity) as total_qty
            FROM invoices
            GROUP BY product
            HAVING total_qty < 5
            ORDER BY total_qty ASC
        ''').fetchall()
        
        return [{"name": p['product'], "qty": p['total_qty']} for p in low_products]
    except:
        return []


def get_growth_analysis(conn):
    """Compare current vs previous revenue"""
    try:
        today = datetime.now()
        current_month_start = today.replace(day=1)
        previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        previous_month_end = current_month_start - timedelta(days=1)
        
        current_revenue = conn.execute('''
            SELECT COALESCE(SUM(total), 0) as total FROM invoices
            WHERE date >= ? AND date <= ?
        ''', (current_month_start.strftime('%d-%m-%Y'), today.strftime('%d-%m-%Y'))).fetchone()['total']
        
        previous_revenue = conn.execute('''
            SELECT COALESCE(SUM(total), 0) as total FROM invoices
            WHERE date >= ? AND date <= ?
        ''', (previous_month_start.strftime('%d-%m-%Y'), previous_month_end.strftime('%d-%m-%Y'))).fetchone()['total']
        
        if previous_revenue == 0:
            growth_percent = 100 if current_revenue > 0 else 0
        else:
            growth_percent = round(((current_revenue - previous_revenue) / previous_revenue) * 100, 1)
        
        return {
            "current": round(current_revenue, 2),
            "previous": round(previous_revenue, 2),
            "growth_percent": growth_percent
        }
    except:
        return {"current": 0, "previous": 0, "growth_percent": 0}


def get_ai_insights(conn):
    """Generate combined AI insights"""
    try:
        total_invoices = conn.execute('SELECT COUNT(*) as count FROM invoices').fetchone()['count']
        total_revenue = conn.execute('SELECT COALESCE(SUM(total), 0) as total FROM invoices').fetchone()['total']
        
        top_product = get_top_product(conn)
        growth = get_growth_analysis(conn)
        low_sales = get_low_sales_alert(conn)
        predicted_revenue = get_revenue_prediction(conn)
        
        insights = []
        
        if total_invoices > 0:
            insights.append(f"📊 Total Invoices: {total_invoices} | Revenue: ₹{total_revenue:.2f}")
        
        if top_product:
            insights.append(f"⭐ Top Product: {top_product['name']} ({top_product['quantity']} units, ₹{top_product['revenue']:.2f})")
        
        if growth['growth_percent'] != 0:
            emoji = "📈" if growth['growth_percent'] > 0 else "📉"
            insights.append(f"{emoji} Sales {'increased' if growth['growth_percent'] > 0 else 'decreased'} by {abs(growth['growth_percent'])}% this month")
        
        if low_sales:
            low_products = ", ".join([f"{p['name']} ({p['qty']} units)" for p in low_sales[:2]])
            insights.append(f"⚠️ Low Sales: {low_products}")
        
        if predicted_revenue:
            insights.append(f"🔮 Predicted Revenue (Next Month): ₹{predicted_revenue:.2f}")
        
        return insights
    except:
        return ["Unable to generate insights at this time"]


def get_sales_chart_data(conn):
    """Get data for sales over time chart"""
    try:
        sales = conn.execute('''
            SELECT date, SUM(total) as revenue, COUNT(*) as invoice_count
            FROM invoices
            GROUP BY date
            ORDER BY date ASC
        ''').fetchall()
        
        dates = [s['date'] for s in sales]
        revenues = [s['revenue'] for s in sales]
        
        return {"dates": dates, "revenues": revenues}
    except:
        return {"dates": [], "revenues": []}


def get_product_quantity_data(conn):
    """Get data for product vs quantity chart"""
    try:
        products = conn.execute('''
            SELECT product, SUM(quantity) as total_qty
            FROM invoices
            GROUP BY product
            ORDER BY total_qty DESC
            LIMIT 10
        ''').fetchall()
        
        names = [p['product'] for p in products]
        quantities = [p['total_qty'] for p in products]
        
        return {"names": names, "quantities": quantities}
    except:
        return {"names": [], "quantities": []}


def get_revenue_distribution_data(conn):
    """Get data for revenue distribution pie chart"""
    try:
        products = conn.execute('''
            SELECT product, SUM(total) as revenue
            FROM invoices
            GROUP BY product
            ORDER BY revenue DESC
            LIMIT 8
        ''').fetchall()
        
        names = [p['product'] for p in products]
        revenues = [round(p['revenue'], 2) for p in products]
        
        return {"names": names, "revenues": revenues}
    except:
        return {"names": [], "revenues": []}


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
# AI HELP ROUTE
# ============================================

@app.route('/ai_help', methods=['POST'])
def ai_help():
    """AI Helper chatbot for user assistance"""
    data = request.get_json()
    query = data.get('query', '').lower().strip()
    
    if not query:
        return jsonify({"response": "Please ask me something!"}), 400
    
    response = ai_chatbot_query(query)
    return jsonify({"response": response})


@app.route('/train_chatbot', methods=['POST'])
@require_role('admin')
def train_chatbot():
    """Admin route to train the chatbot"""
    try:
        question = request.form.get('question', '').strip().lower()
        answer = request.form.get('answer', '').strip()
        
        if not question or not answer:
            flash('Both question and answer are required.', 'warning')
            return redirect(url_for('admin_dashboard'))
        
        conn = get_db_connection()
        
        # Check if question exists
        existing = conn.execute(
            "SELECT id FROM chatbot_training WHERE question=?", 
            (question,)
        ).fetchone()
        
        if existing:
            conn.execute(
                "UPDATE chatbot_training SET answer=? WHERE question=?", 
                (answer, question)
            )
            flash('Chatbot training updated successfully.', 'success')
        else:
            conn.execute(
                "INSERT INTO chatbot_training (question, answer) VALUES (?, ?)", 
                (question, answer)
            )
            flash('Chatbot training added successfully.', 'success')
        
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'Error training chatbot: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))


# ============================================
# API ROUTES FOR FRONTEND
# ============================================

@app.route('/api/calculate_tax', methods=['POST'])
def api_calculate_tax():
    """Calculate tax for given subtotal"""
    data = request.get_json()
    try:
        subtotal = float(data.get('subtotal', 0))
        result = calculate_tax(subtotal)
        result['subtotal'] = subtotal
        return jsonify(result)
    except:
        return jsonify({"error": "Invalid input"}), 400


@app.route('/api/generate_email/<int:invoice_id>')
def api_generate_email(invoice_id):
    """Generate email preview for an invoice"""
    if not session.get('username'):
        return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db_connection()
    invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
    conn.close()
    
    if not invoice:
        return jsonify({"error": "Invoice not found"}), 404
    
    email_content = generate_email(invoice['customer'], invoice['product'], invoice['total'], invoice['id'])
    return jsonify({"email": email_content})

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
    
    # Get AI insights
    ai_insights = get_ai_insights(conn)
    
    # Get chart data
    sales_chart = get_sales_chart_data(conn)
    product_qty_chart = get_product_quantity_data(conn)
    revenue_dist_chart = get_revenue_distribution_data(conn)
    
    conn.close()

    return render_template(
        'admin/dashboard.html',
        invoice_count=invoice_count,
        total_revenue=total_revenue,
        customer_count=customer_count,
        recent_invoices=recent_invoices,
        ai_insights=ai_insights,
        sales_chart_data=json.dumps(sales_chart),
        product_qty_chart_data=json.dumps(product_qty_chart),
        revenue_dist_chart_data=json.dumps(revenue_dist_chart)
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
        product_gst = request.form.get('product_gst', '0.18').strip()

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

            conn.execute(
                'INSERT INTO products (name, price, gst, created_date) VALUES (?, ?, ?, ?)',
                (product_name, product_price, product_gst, datetime.now().strftime('%d-%m-%Y'))
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
    
    # Get AI insights
    ai_insights = get_ai_insights(conn)
    
    # Get chart data
    sales_chart = get_sales_chart_data(conn)
    product_qty_chart = get_product_quantity_data(conn)
    revenue_dist_chart = get_revenue_distribution_data(conn)
    
    conn.close()

    return render_template(
        'user/dashboard.html',
        invoices=invoices,
        total_revenue=total_revenue,
        ai_insights=ai_insights,
        sales_chart_data=json.dumps(sales_chart),
        product_qty_chart_data=json.dumps(product_qty_chart),
        revenue_dist_chart_data=json.dumps(revenue_dist_chart),
        email_preview=session.pop('invoice_email_preview', None)
    )


@app.route('/create_invoice', methods=['GET', 'POST'])
@require_role('user')
def create_invoice():
    conn = get_db_connection()
    
    if request.method == 'POST':
        customer = request.form.get('customer', '').strip()
        product_id = request.form.get('product_id', '').strip()
        quantity = request.form.get('quantity', '').strip()

        try:
            # Validate inputs
            if not customer:
                raise ValueError('Customer name is required.')
            if not product_id:
                raise ValueError('Product is required.')
            if not quantity:
                raise ValueError('Quantity is required.')
            
            # Convert and validate types
            try:
                product_id = int(product_id)
                quantity = int(quantity)
            except ValueError:
                raise ValueError('Invalid product or quantity.')
            
            # Validate values
            if quantity <= 0:
                raise ValueError('Quantity must be greater than zero.')
            
            # Get product details
            product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
            if not product:
                raise ValueError('Product not found.')

            price = float(product['price'])
            product_name = product['name']
            gst_rate = float(product['gst'] if product['gst'] is not None else 0.18)
            
            subtotal = round(quantity * price, 2)
            tax_calc = calculate_tax(subtotal, gst_rate)
            total = tax_calc['final_total']
            date = datetime.now().strftime('%d-%m-%Y')

            conn.execute(
                'INSERT INTO invoices (customer, product, quantity, price, total, date, created_by, product_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (customer, product_name, quantity, price, total, date, session.get('username'), product_id)
            )
            conn.commit()
            
            session['invoice_email_preview'] = generate_email(customer, product_name, total, 0)
            flash('Invoice created successfully.', 'success')
            return redirect(url_for('user_dashboard'))

        except ValueError as error:
            flash(str(error), 'danger')
        except Exception as e:
            flash(f'Error creating invoice: {str(e)}', 'danger')

    products = conn.execute('SELECT * FROM products ORDER BY name').fetchall()
    conn.close()
    
    return render_template('user/create_invoice.html', products=products)


@app.route('/api/product_price/<int:product_id>')
@require_role('user')
def api_product_price(product_id):
    """Get product price for real-time calculation"""
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()
    
    if not product:
        return jsonify({"error": "Product not found"}), 404
    
    return jsonify({"price": product['price']})


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




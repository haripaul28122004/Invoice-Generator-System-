import sys
if __name__ == '__main__':
    sys.modules['app'] = sys.modules['__main__']

from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file, jsonify
from flask_mail import Mail, Message
import sqlite3
import io
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

from functools import wraps
import json
import os, glob, shutil

try:
    from model import train_model, predict_price as ai_predict_price, \
                      predict_revenue, predict_best_product
    AI_ENABLED = True
except ImportError:
    AI_ENABLED = False
    def train_model(products): pass
    def ai_predict_price(cat, qty, base): return base
    def predict_revenue(db_path='database.db'): return {'predicted': 0.0, 'confidence': 'low', 'data_points': 0}
    def predict_best_product(db_path='database.db'): return None

try:
    import pdfkit

    # ── 1. Try every known install location ───────────────────────
    _WKHTMLTOPDF_CANDIDATES = [
        r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'C:\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'D:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
        r'D:\wkhtmltopdf\bin\wkhtmltopdf.exe',
        os.path.expanduser(r'~\wkhtmltopdf\bin\wkhtmltopdf.exe'),
    ]

    print("[pdfkit] Scanning for wkhtmltopdf.exe ...")
    for _p in _WKHTMLTOPDF_CANDIDATES:
        print(f"  {'FOUND' if os.path.exists(_p) else 'not found':10s} {_p}")

    _WKHTMLTOPDF = next(
        (p for p in _WKHTMLTOPDF_CANDIDATES if os.path.exists(p)), None
    )

    # ── 2. Try system PATH ────────────────────────────────────────
    if not _WKHTMLTOPDF:
        _WKHTMLTOPDF = shutil.which('wkhtmltopdf')
        if _WKHTMLTOPDF:
            print(f"[pdfkit] Found via system PATH: {_WKHTMLTOPDF}")

    # ── 3. Build config or warn ───────────────────────────────────
    if _WKHTMLTOPDF:
        _PDFKIT_CONFIG = pdfkit.configuration(wkhtmltopdf=_WKHTMLTOPDF)
        print(f"[pdfkit] READY — using: {_WKHTMLTOPDF}")
    else:
        _PDFKIT_CONFIG = None
        print("[pdfkit] *** wkhtmltopdf.exe NOT FOUND on this system. ***")
        print("[pdfkit] Download installer: https://wkhtmltopdf.org/downloads.html")
        print("[pdfkit] Install to default path, then restart Flask.")

except ImportError:
    pdfkit = None
    _PDFKIT_CONFIG = None
    print("[pdfkit] WARNING: pdfkit not installed. Run: pip install pdfkit")

app = Flask(__name__)
app.secret_key = 'invoice_flow_secret_key_2026'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
DATABASE = 'database.db'
ADMIN_EMAIL = 'haripaul28122004@gmail.com'
ADMIN_PASSWORD = 'haripaul007'

# ============================================
# EMAIL CONFIGURATION
# ============================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'haripaul28122004@gmail.com'  
app.config['MAIL_PASSWORD'] = 'yvxfavdfzlctkozd'  
app.config['MAIL_DEFAULT_SENDER'] = 'haripaul28122004@gmail.com' 

mail = Mail(app)


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
            category TEXT DEFAULT 'General',
            price REAL NOT NULL,
            gst REAL NOT NULL DEFAULT 0.18,
            stock INTEGER DEFAULT 0,
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
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS invoice_items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            product_id INTEGER,
            product    TEXT NOT NULL,
            quantity   INTEGER NOT NULL,
            price      REAL NOT NULL,
            gst_rate   REAL NOT NULL DEFAULT 0.18,
            line_total REAL NOT NULL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        )
    ''')

    # Migration: add new columns if they don't exist
    try:
        cur.execute("PRAGMA table_info(products)")
        prod_cols = [col[1] for col in cur.
        fetchall()]
        if 'category' not in prod_cols:
            cur.execute("ALTER TABLE products ADD COLUMN category TEXT DEFAULT 'General'")
        if 'stock' not in prod_cols:
            cur.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0")

        cur.execute("PRAGMA table_info(invoices)")
        inv_cols = [col[1] for col in cur.fetchall()]
        if 'customer_email' not in inv_cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN customer_email TEXT DEFAULT ''")
        if 'customer_address' not in inv_cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN customer_address TEXT DEFAULT ''")
        if 'gst_rate' not in inv_cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN gst_rate REAL DEFAULT 0.18")
        if 'gst_amount' not in inv_cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN gst_amount REAL DEFAULT 0")
        if 'last_updated' not in inv_cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN last_updated TEXT DEFAULT ''")

        # Seed invoice_items from existing single-product invoices (backward compat)
        cur.execute('''
            INSERT INTO invoice_items (invoice_id, product_id, product, quantity, price, gst_rate, line_total)
            SELECT id, product_id, product, quantity, price,
                   COALESCE(gst_rate, 0.18),
                   ROUND(quantity * price, 2)
            FROM invoices
            WHERE id NOT IN (SELECT DISTINCT invoice_id FROM invoice_items)
              AND product IS NOT NULL
        ''')

        conn.commit()
    except Exception as e:
        print(f"Migration note: {e}")

    conn.close()


def seed_employee():
    """Upsert the default employee user on every startup.

    - If the user does not exist → INSERT with a fresh password hash.
    - If the user already exists → UPDATE password hash + role so stale
      or plaintext passwords never block login.
    """
    conn = sqlite3.connect(DATABASE)
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT id FROM users WHERE email = ?",
        ("haripaul282004@gmail.com",)
    ).fetchone()

    hashed = generate_password_hash("haripaul123")

    if not existing:
        cur.execute(
            "INSERT INTO users (username, email, password, role) VALUES (?, ?, ?, ?)",
            (
                "Hari Paul",
                "haripaul282004@gmail.com",
                hashed,
                "user"
            )
        )
        print("[OK] Employee user created: haripaul282004@gmail.com")
    else:
        # Always refresh hash + role so a stale record never blocks login
        cur.execute(
            "UPDATE users SET username = ?, password = ?, role = ? WHERE email = ?",
            ("Hari Paul", hashed, "user", "haripaul282004@gmail.com")
        )
        print("[OK] Employee user refreshed: haripaul282004@gmail.com")

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


def _generate_pdf_bytes(invoice_dict, items=None):
    """Render invoice_pdf.html and convert to PDF bytes via pdfkit/wkhtmltopdf."""
    print("USING NEW PDF SYSTEM")
    if not pdfkit or not _PDFKIT_CONFIG:
        raise RuntimeError(
            "wkhtmltopdf not found. Install it from https://wkhtmltopdf.org/downloads.html "
            "to C:\\Program Files\\wkhtmltopdf\\ and restart the server."
        )
    html_str = render_template('invoice_pdf.html', invoice=invoice_dict, items=items or [])
    options = {
        'page-size':      'A4',
        'margin-top':     '10mm',
        'margin-right':   '10mm',
        'margin-bottom':  '10mm',
        'margin-left':    '10mm',
        'encoding':       'UTF-8',
        'no-outline':     None,
        'enable-local-file-access': None,
    }
    return pdfkit.from_string(html_str, False,
                              configuration=_PDFKIT_CONFIG,
                              options=options)


def _number_to_words(amount):
    """Convert a number to Indian English words for amount-in-words line."""
    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
            'Eight', 'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen',
            'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty',
            'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def two_digits(n):
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')).strip()

    def three_digits(n):
        if n == 0:
            return ''
        h = n // 100
        r = n % 100
        parts = []
        if h:
            parts.append(ones[h] + ' Hundred')
        if r:
            parts.append(two_digits(r))
        return ' '.join(parts)

    n = int(round(amount))
    if n == 0:
        return 'Zero'
    parts = []
    crore = n // 10000000;  n %= 10000000
    lakh  = n // 100000;    n %= 100000
    thousand = n // 1000;   n %= 1000
    remainder = n
    if crore:
        parts.append(three_digits(crore) + ' Crore')
    if lakh:
        parts.append(three_digits(lakh) + ' Lakh')
    if thousand:
        parts.append(three_digits(thousand) + ' Thousand')
    if remainder:
        parts.append(three_digits(remainder))
    return ' '.join(parts)


def build_invoice_pdf(invoice):
    """Build an Amazon-style professional PDF for an invoice and return raw bytes."""
    # Convert sqlite3.Row (or any mapping) to a plain dict so .get() works
    invoice = dict(invoice)
    print("INVOICE DATA:", invoice)

    # ── Style helpers ──────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30
    )
    styles = getSampleStyleSheet()
    W = A4[0] - 60          # usable width (points)

    def style(name='Normal', **kw):
        return ParagraphStyle(name, parent=styles[name], **kw)

    BRAND   = colors.HexColor('#131921')   # Amazon dark header
    ACCENT  = colors.HexColor('#FF9900')   # Amazon orange
    LIGHT   = colors.HexColor('#F3F3F3')
    MID     = colors.HexColor('#D5D9D9')
    WHITE   = colors.white
    DARK    = colors.HexColor('#0F1111')
    MUTED   = colors.HexColor('#565959')

    s_normal  = style('Normal', fontSize=8,  leading=12, textColor=DARK)
    s_small   = style('Normal', fontSize=7,  leading=10, textColor=MUTED)
    s_bold    = style('Normal', fontSize=8,  leading=12, textColor=DARK,
                      fontName='Helvetica-Bold')
    s_heading = style('Normal', fontSize=9,  leading=13, textColor=DARK,
                      fontName='Helvetica-Bold')
    s_brand   = style('Normal', fontSize=20, leading=24, textColor=WHITE,
                      fontName='Helvetica-Bold')
    s_inv_lbl = style('Normal', fontSize=9,  leading=13, textColor=WHITE)
    s_inv_big = style('Normal', fontSize=22, leading=26, textColor=ACCENT,
                      fontName='Helvetica-Bold')
    s_right   = style('Normal', fontSize=8,  leading=12, textColor=DARK,
                      alignment=TA_RIGHT)
    s_right_b = style('Normal', fontSize=8,  leading=12, textColor=DARK,
                      fontName='Helvetica-Bold', alignment=TA_RIGHT)
    s_total_r = style('Normal', fontSize=9,  leading=14, textColor=WHITE,
                      fontName='Helvetica-Bold', alignment=TA_RIGHT)

    elements = []

    # ══════════════════════════════════════════════════════════════
    # PART 1 — HEADER: Company (left) | INVOICE label (right)
    # ══════════════════════════════════════════════════════════════
    company_block = Paragraph(
        '<b><font size="14">InvoiceFlow</font></b><br/>'
        '<font size="7" color="#AAAAAA">GSTIN: 22ABCDE1234F1Z5</font><br/>'
        '<font size="7" color="#AAAAAA">Hyderabad, Telangana – 500001</font><br/>'
        '<font size="7" color="#AAAAAA">Ph: +91-9999999999 | info@invoiceflow.in</font>',
        s_brand
    )
    inv_id   = invoice.get('id', 0)
    inv_date = invoice.get('date', 'N/A')
    invoice_block = [
        [Paragraph('INVOICE', s_inv_big)],
        [Paragraph('Original for Recipient', s_inv_lbl)],
        [Paragraph(f'Invoice No: <b>INV-{inv_id:05d}</b>', s_inv_lbl)],
        [Paragraph(f'Date: <b>{inv_date}</b>', s_inv_lbl)],
    ]
    inv_inner = Table(invoice_block, colWidths=[W * 0.38])
    inv_inner.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))

    header_tbl = Table(
        [[company_block, inv_inner]],
        colWidths=[W * 0.60, W * 0.40]
    )
    header_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BRAND),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 16),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 16),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
    ]))
    elements.append(header_tbl)
    elements.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════
    # PART 2 — Orange accent bar
    # ══════════════════════════════════════════════════════════════
    accent_bar = Table([['']], colWidths=[W])
    accent_bar.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), ACCENT),
        ('TOPPADDING',    (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(accent_bar)
    elements.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════
    # PART 3 — 3-COLUMN: Customer | Billing | Shipping
    # ══════════════════════════════════════════════════════════════
    addr     = invoice.get('customer_address', '') or 'N/A'
    email    = invoice.get('customer_email', '')  or 'N/A'
    customer = invoice.get('customer', 'N/A')     or 'N/A'
    col_w = W / 3.0

    cust_para = Paragraph(
        f'<b>Customer Details</b><br/>'
        f'<font size="8">{customer}</font><br/>'
        f'<font size="7" color="#565959">{email}</font>',
        s_normal
    )
    bill_para = Paragraph(
        f'<b>Billing Address</b><br/>'
        f'<font size="8">{addr}</font>',
        s_normal
    )
    ship_para = Paragraph(
        f'<b>Shipping Address</b><br/>'
        f'<font size="8">{addr}</font>',
        s_normal
    )

    addr_tbl = Table([[cust_para, bill_para, ship_para]],
                     colWidths=[col_w, col_w, col_w])
    addr_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT),
        ('BOX',           (0, 0), (-1, -1), 0.5, MID),
        ('INNERGRID',     (0, 0), (-1, -1), 0.5, MID),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    elements.append(addr_tbl)
    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════
    # PART 4 — PRODUCT TABLE (Amazon-style 7 columns)
    # ══════════════════════════════════════════════════════════════
    gst_rate = 0.18
    try:
        conn_pdf = sqlite3.connect(DATABASE)
        row = conn_pdf.execute(
            'SELECT gst FROM products WHERE id = ?', (invoice.get('product_id') or 0,)
        ).fetchone()
        if row and row[0]:
            gst_rate = float(row[0])
        conn_pdf.close()
    except Exception:
        pass

    price    = float(invoice.get('price', 0) or 0)
    qty      = int(invoice.get('quantity', 0) or 0)
    taxable  = round(price * qty, 2)
    gst_amt  = round(taxable * gst_rate, 2)
    grand    = round(taxable + gst_amt, 2)
    gst_pct  = int(round(gst_rate * 100))

    # Column widths: #, Item, Rate, Qty, Taxable Value, Tax Amount, Total
    cw = [22, 170, 65, 38, 80, 80, 77]

    def hdr_p(txt):
        return Paragraph(f'<font color="white"><b>{txt}</b></font>', s_normal)

    def cell_p(txt, right=False):
        return Paragraph(txt, s_right if right else s_normal)

    prod_name = invoice.get('product', 'N/A') or 'N/A'
    category  = ''
    try:
        conn_pdf2 = sqlite3.connect(DATABASE)
        pr = conn_pdf2.execute(
            'SELECT category FROM products WHERE id = ?', (invoice.get('product_id') or 0,)
        ).fetchone()
        if pr:
            category = pr[0] or ''
        conn_pdf2.close()
    except Exception:
        pass

    item_cell = Paragraph(
        f'<b>{prod_name}</b><br/>'
        f'<font size="7" color="#565959">Category: {category} &nbsp;|&nbsp; '
        f'HSN: 8471 &nbsp;|&nbsp; GST: {gst_pct}%</font>',
        s_normal
    )

    table_data = [
        [hdr_p('#'), hdr_p('Item'), hdr_p('Rate'),
         hdr_p('Qty'), hdr_p('Taxable Value'),
         hdr_p('Tax Amount'), hdr_p('Total')],
        [
            cell_p('1'),
            item_cell,
            cell_p(f'Rs.{price:,.2f}', right=True),
            cell_p(str(qty)),
            cell_p(f'Rs.{taxable:,.2f}', right=True),
            cell_p(f'Rs.{gst_amt:,.2f}', right=True),
            cell_p(f'Rs.{grand:,.2f}', right=True),
        ]
    ]

    prod_tbl = Table(table_data, colWidths=cw)
    prod_tbl.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',    (0, 0), (-1, 0), BRAND),
        ('TEXTCOLOR',     (0, 0), (-1, 0), WHITE),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        # Data row
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [WHITE, LIGHT]),
        ('FONTSIZE',      (0, 0), (-1, -1), 8),
        # Alignment
        ('ALIGN',  (0, 0), (0, -1), 'CENTER'),
        ('ALIGN',  (2, 0), (2, -1), 'RIGHT'),
        ('ALIGN',  (4, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        # Grid & padding
        ('GRID',          (0, 0), (-1, -1), 0.4, MID),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    elements.append(prod_tbl)
    elements.append(Spacer(1, 14))

    # ══════════════════════════════════════════════════════════════
    # PART 5 — GST BREAKDOWN (right-aligned, Amazon-style)
    # ══════════════════════════════════════════════════════════════
    left_w  = W * 0.55
    right_w = W * 0.45

    gst_rows = [
        [Paragraph('Taxable Amount', s_right),
         Paragraph(f'Rs.{taxable:,.2f}', s_right_b)],
        [Paragraph(f'IGST {gst_pct}%', s_right),
         Paragraph(f'Rs.{gst_amt:,.2f}', s_right_b)],
    ]
    gst_inner = Table(gst_rows, colWidths=[right_w * 0.55, right_w * 0.45])
    gst_inner.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('LINEBELOW',     (0, -1), (-1, -1), 0.5, MID),
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT),
    ]))

    total_row = Table(
        [[Paragraph('Grand Total', s_total_r),
          Paragraph(f'Rs.{grand:,.2f}', s_total_r)]],
        colWidths=[right_w * 0.55, right_w * 0.45]
    )
    total_row.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BRAND),
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',    (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))

    summary_outer = Table(
        [['', gst_inner], ['', total_row]],
        colWidths=[left_w, right_w]
    )
    summary_outer.setStyle(TableStyle([
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    elements.append(summary_outer)
    elements.append(Spacer(1, 16))

    # ══════════════════════════════════════════════════════════════
    # PART 6 — AMOUNT IN WORDS
    # ══════════════════════════════════════════════════════════════
    words = _number_to_words(grand)
    words_tbl = Table(
        [[Paragraph(
            f'<b>Amount in Words:</b> &nbsp;INR {words} Only',
            style('Normal', fontSize=8, leading=12, textColor=DARK)
        )]],
        colWidths=[W]
    )
    words_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT),
        ('BOX',           (0, 0), (-1, -1), 0.5, MID),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    elements.append(words_tbl)
    elements.append(Spacer(1, 20))

    # ══════════════════════════════════════════════════════════════
    # PART 7 — FOOTER
    # ══════════════════════════════════════════════════════════════
    footer_tbl = Table(
        [[Paragraph(
            '<font size="8" color="#AAAAAA">Thank you for your business. '
            'This is a computer-generated invoice and requires no signature. '
            '| Generated by <b>InvoiceFlow</b></font>',
            s_normal
        )]],
        colWidths=[W]
    )
    footer_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BRAND),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 14),
    ]))
    elements.append(footer_tbl)

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


def send_invoice_email(email, name, total, pdf_data=None):
    """Send a professional invoice email with optional PDF attachment."""
    try:
        if not email or '@' not in email:
            print(f"Invalid email address: {email}")
            return False

        now_str = datetime.now().strftime('%d-%m-%Y')
        msg = Message(
            subject="Your Invoice from InvoiceFlow",
            recipients=[email]
        )

        # Plain-text fallback
        msg.body = f"""Dear {name},

We hope this message finds you well.

Please find attached your invoice for the recent transaction.

Invoice Summary:
  Total Amount : ₹{total:.2f}
  Date         : {now_str}

If you have any questions, feel free to contact us.

Thank you for your business.

Best regards,
InvoiceFlow Team
"""

        # Rich HTML body
        msg.html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr><td align="center" style="padding:32px 0;">
      <table width="580" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;
                    box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden;">

        <!-- Header -->
        <tr>
          <td style="background:#4f46e5;padding:28px 32px;">
            <h1 style="margin:0;color:#ffffff;font-size:22px;">InvoiceFlow</h1>
            <p  style="margin:4px 0 0;color:#c7d2fe;font-size:13px;">Invoice Notification</p>
          </td>
        </tr>

        <!-- Greeting -->
        <tr><td style="padding:28px 32px 0;">
          <p style="margin:0;font-size:15px;color:#1e293b;">Dear <strong>{name}</strong>,</p>
          <p style="margin:12px 0 0;font-size:14px;color:#475569;line-height:1.6;">
            We hope this message finds you well.<br>
            Please find your invoice attached to this email.
          </p>
        </td></tr>

        <!-- Summary card -->
        <tr><td style="padding:24px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#f8fafc;border:1px solid #e2e8f0;
                        border-radius:6px;border-left:4px solid #4f46e5;">
            <tr>
              <td style="padding:18px 20px;">
                <p style="margin:0 0 6px;font-size:11px;text-transform:uppercase;
                          letter-spacing:1px;color:#64748b;">Invoice Summary</p>
                <table width="100%">
                  <tr>
                    <td style="font-size:13px;color:#475569;">Total Amount</td>
                    <td align="right" style="font-size:18px;font-weight:bold;
                                            color:#4f46e5;">₹{total:,.2f}</td>
                  </tr>
                  <tr>
                    <td style="font-size:13px;color:#475569;padding-top:6px;">Date</td>
                    <td align="right" style="font-size:13px;color:#475569;
                                            padding-top:6px;">{now_str}</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td></tr>

        <!-- Note -->
        <tr><td style="padding:0 32px 24px;">
          <p style="margin:0;font-size:13px;color:#64748b;line-height:1.6;">
            If you have any questions regarding this invoice, please don't
            hesitate to contact us.
          </p>
        </td></tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:18px 32px;
                     border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:12px;color:#94a3b8;">
              Thank you for your business &mdash;
              <strong style="color:#4f46e5;">InvoiceFlow Team</strong>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

        # Attach PDF if provided
        if pdf_data:
            msg.attach(
                filename='invoice.pdf',
                content_type='application/pdf',
                data=pdf_data
            )

        mail.send(msg)
        print(f"✓ Email sent successfully to {email}")
        return True

    except Exception as e:
        print(f"✗ Email Error: {str(e)}")
        return False


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
    """Predict next month revenue using the RandomForest model in model.py."""
    try:
        result = predict_revenue(DATABASE)
        return result.get('predicted', 0.0)
    except Exception:
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
                    return redirect(url_for('admin.admin_dashboard'))
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
    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))
    elif session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))
    elif session.get('role') == 'customer':
        return redirect(url_for('customer_dashboard'))
    return render_template('index.html')


# ============================================
# SEED DATA ROUTE
# ============================================

@app.route('/seed_data')
def seed_data():
    """Initialize sample products into the database"""
    try:
        conn = get_db_connection()
        
        # Check if products already exist
        existing = conn.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
        
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
                conn.execute(
                    'INSERT INTO products (name, category, price, gst, stock, created_date) VALUES (?, ?, ?, ?, ?, ?)',
                    (name, category, price, gst, stock, datetime.now().strftime('%d-%m-%Y'))
                )
            
            conn.commit()
            conn.close()
            return jsonify({"status": "success", "message": f"Created {len(sample_products)} sample products"})
        else:
            conn.close()
            return jsonify({"status": "info", "message": f"Database already has {existing} products"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


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

        session.permanent = True
        session['username'] = email
        session['role'] = 'admin'
        session['user_id'] = 0
        flash('Admin logged in successfully.', 'success')
        return redirect(url_for('admin.admin_dashboard'))

    if session.get('role') == 'admin':
        return redirect(url_for('admin.admin_dashboard'))

    return render_template('admin/login.html')



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

        session.permanent = True
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
    return render_template(
        'user/dashboard.html',
        invoices=invoices,
        total_revenue=total_revenue,
        email_preview=session.pop('invoice_email_preview', None)
    )


@app.route('/create_invoice', methods=['GET', 'POST'])
@require_role('user')
def create_invoice():
    conn = get_db_connection()

    if request.method == 'POST':
        customer         = request.form.get('customer', '').strip()
        customer_email   = request.form.get('customer_email', '').strip()
        customer_address = request.form.get('customer_address', '').strip()

        # Multi-product arrays
        product_ids = request.form.getlist('product_id[]')
        quantities  = request.form.getlist('quantity[]')

        try:
            if not customer:
                raise ValueError('Customer name is required.')
            if not customer_email or '@' not in customer_email:
                raise ValueError('A valid customer email is required.')
            if not customer_address:
                raise ValueError('Customer address is required.')
            if not product_ids:
                raise ValueError('At least one product is required.')

            date = datetime.now().strftime('%d-%m-%Y')
            subtotal   = 0.0
            item_rows  = []   # (product_id, product_name, qty, price, gst_rate, line_total)

            for i, pid_str in enumerate(product_ids):
                qty_str = quantities[i] if i < len(quantities) else '0'
                try:
                    pid = int(pid_str)
                    qty = int(qty_str)
                except ValueError:
                    raise ValueError(f'Invalid product or quantity on row {i+1}.')

                if qty <= 0:
                    raise ValueError(f'Quantity on row {i+1} must be greater than zero.')

                product = conn.execute('SELECT * FROM products WHERE id = ?', (pid,)).fetchone()
                if not product:
                    raise ValueError(f'Product on row {i+1} not found.')

                stock = product['stock'] if product['stock'] is not None else 0
                if stock < qty:
                    raise ValueError(f'Insufficient stock for "{product["name"]}". Available: {stock}, Requested: {qty}')

                price      = float(product['price'])
                gst_rate   = float(product['gst'] if product['gst'] is not None else 0.18)
                line_total = round(qty * price, 2)
                subtotal  += line_total
                item_rows.append((pid, product['name'], qty, price, gst_rate, line_total))

            # Use weighted-average GST for the invoice header
            avg_gst    = item_rows[0][4] if len(item_rows) == 1 else 0.18
            gst_amount = round(subtotal * avg_gst, 2)
            grand_total = round(subtotal + gst_amount, 2)
            first_product = item_rows[0][1]   # for dashboard list compat

            # ── Insert invoice header ────────────────────────────────
            cursor = conn.execute(
                '''INSERT INTO invoices
                   (customer, customer_email, customer_address,
                    product, quantity, price, total, gst_rate, gst_amount,
                    date, created_by, product_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (customer, customer_email, customer_address,
                 first_product, item_rows[0][2], item_rows[0][3],
                 grand_total, avg_gst, gst_amount,
                 date, session.get('username'), item_rows[0][0])
            )
            invoice_id = cursor.lastrowid

            # ── Insert line items + deduct stock ─────────────────────
            for pid, pname, qty, price, gst_rate, line_total in item_rows:
                conn.execute(
                    '''INSERT INTO invoice_items
                       (invoice_id, product_id, product, quantity, price, gst_rate, line_total)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (invoice_id, pid, pname, qty, price, gst_rate, line_total)
                )
                conn.execute(
                    'UPDATE products SET stock = stock - ? WHERE id = ?',
                    (qty, pid)
                )

            conn.commit()

            # Fetch saved invoice + items for email PDF
            new_invoice = conn.execute(
                'SELECT * FROM invoices WHERE id = ?', (invoice_id,)
            ).fetchone()
            new_items = conn.execute(
                'SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,)
            ).fetchall()
            conn.close()

            # Email with PDF — non-fatal
            try:
                pdf_bytes = _generate_pdf_bytes(dict(new_invoice), [dict(r) for r in new_items])
                send_invoice_email(customer_email, customer, grand_total, pdf_data=pdf_bytes)
                flash('Invoice created successfully and email sent with PDF.', 'success')
            except Exception as email_err:
                print(f"Email failed (non-fatal): {email_err}")
                flash('Invoice created successfully. Email could not be sent.', 'warning')

            session['invoice_email_preview'] = generate_email(customer, first_product, grand_total, 0)
            return redirect(url_for('user_dashboard'))

        except ValueError as error:
            conn.close()
            flash(str(error), 'danger')
            return redirect(url_for('create_invoice'))
        except Exception as e:
            print(f"ERROR create_invoice: {e}")
            conn.close()
            flash(f'Unexpected error creating invoice: {str(e)}', 'danger')
            return redirect(url_for('create_invoice'))

    # GET — load product dropdown (dicts so tojson can serialize them)
    products = [dict(r) for r in conn.execute(
        'SELECT * FROM products ORDER BY category, name'
    ).fetchall()]
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

        session.permanent = True
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
    customer_email = session.get('email')

    print(f"DEBUG customer_dashboard: email={customer_email!r}")

    # Match invoices by the email supplied when the employee created the invoice
    invoices = conn.execute(
        'SELECT * FROM invoices WHERE customer_email = ? ORDER BY id DESC',
        (customer_email,)
    ).fetchall()

    totals = conn.execute(
        'SELECT COALESCE(SUM(total), 0) AS revenue FROM invoices WHERE customer_email = ?',
        (customer_email,)
    ).fetchone()
    total_revenue = totals['revenue'] if totals else 0

    print(f"DEBUG customer_dashboard: found {len(invoices)} invoice(s), total=₹{total_revenue}")
    conn.close()

    return render_template('customer/dashboard.html', invoices=invoices, total_revenue=total_revenue)


@app.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    if not session.get('username'):
        return redirect(url_for('home'))

    conn = get_db_connection()
    invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()

    if invoice is None:
        conn.close()
        flash('Invoice not found.', 'warning')
        role = session.get('role')
        if role == 'admin': return redirect(url_for('admin_dashboard'))
        if role == 'user':  return redirect(url_for('user_dashboard'))
        if role == 'customer': return redirect(url_for('customer_dashboard'))
        return redirect(url_for('home'))

    # Access control for customers
    if session.get('role') == 'customer':
        session_email = (session.get('email') or '').strip().lower()
        invoice_email = (invoice['customer_email'] or '').strip().lower()
        print(f"VIEW_INVOICE — SESSION EMAIL: {session_email!r}  |  INVOICE EMAIL: {invoice_email!r}")
        if session_email != invoice_email:
            conn.close()
            flash('You do not have access to this invoice.', 'danger')
            return redirect(url_for('customer_dashboard'))

    items = conn.execute(
        'SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id', (invoice_id,)
    ).fetchall()
    conn.close()

    return render_template('invoice.html', invoice=dict(invoice), items=[dict(r) for r in items])

@app.route('/admin/customer/<customer>/invoices')
@require_role('admin')
def admin_customer_invoices(customer):
    conn = get_db_connection()

    invoices = conn.execute(
        'SELECT * FROM invoices WHERE customer=? ORDER BY id DESC',
        (customer,)
    ).fetchall()

    conn.close()

    return render_template(
        'admin/customer_invoices.html',
        invoices=invoices,
        customer=customer
    )

@app.route('/admin/invoice/<int:invoice_id>/edit', methods=['GET', 'POST'])
@require_role('admin')
def edit_invoice(invoice_id):
    conn = get_db_connection()

    if request.method == 'POST':
        customer = request.form.get('customer')
        quantity = request.form.get('quantity')

        conn.execute(
            'UPDATE invoices SET customer=?, quantity=? WHERE id=?',
            (customer, quantity, invoice_id)
        )

        conn.commit()
        conn.close()

        flash('Invoice updated successfully', 'success')
        return redirect(url_for('admin.admin_dashboard'))

    invoice = conn.execute(
        'SELECT * FROM invoices WHERE id=?',
        (invoice_id,)
    ).fetchone()

    conn.close()

    return render_template('admin/edit_invoice.html', invoice=invoice)

@app.route('/invoice/<int:invoice_id>/download')
def download_invoice(invoice_id):
    if not session.get('username'):
        return redirect(url_for('home'))

    conn = get_db_connection()
    invoice = conn.execute('SELECT * FROM invoices WHERE id = ?', (invoice_id,)).fetchone()
    conn.close()

    if invoice is None:
        flash('Invoice not found.', 'warning')
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'user':
            return redirect(url_for('user_dashboard'))
        elif role == 'customer':
            return redirect(url_for('customer_dashboard'))
        return redirect(url_for('home'))

    # Access control for customers: match by email (not name)
    if session.get('role') == 'customer':
        session_email = (session.get('email') or '').strip().lower()
        invoice_email = (invoice['customer_email'] or '').strip().lower()
        print(f"DOWNLOAD_INVOICE — SESSION EMAIL: {session_email!r}  |  INVOICE EMAIL: {invoice_email!r}")
        if session_email != invoice_email:
            flash('You do not have access to this invoice.', 'danger')
            return redirect(url_for('customer_dashboard'))

    print(f"Downloading invoice: {invoice_id}  |  customer: {invoice['customer']!r}")
    invoice_dict = dict(invoice)

    # Fetch line items
    conn2 = get_db_connection()
    items = [dict(r) for r in conn2.execute(
        'SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id', (invoice_id,)
    ).fetchall()]
    conn2.close()

    try:
        pdf_bytes = _generate_pdf_bytes(invoice_dict, items)
        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=f"invoice_{invoice_dict['id']}.pdf",
            mimetype='application/pdf'
        )
    except Exception as e:
        print(f"PDF ERROR for invoice {invoice_id}: {e}")
        flash(f'Error generating PDF: {e}', 'danger')
        role = session.get('role')
        if role == 'customer':
            return redirect(url_for('customer_dashboard'))
        elif role == 'user':
            return redirect(url_for('user_dashboard'))
        return redirect(url_for('admin.admin_dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))





# ── Always initialise DB, regardless of launch method ───────────────────
with app.app_context():
    init_db()
    seed_employee()

    # ── Train AI price model on real product data ────────────────────────
    if AI_ENABLED:
        try:
            _conn = sqlite3.connect(DATABASE)
            _conn.row_factory = sqlite3.Row
            _products = [dict(r) for r in
                         _conn.execute('SELECT name, category, price FROM products').fetchall()]
            _conn.close()
            train_model(_products)
        except Exception as _e:
            print(f'[AI] Model training skipped: {_e}')

# ── AI Price Prediction API ───────────────────────────────────────────────
@app.route('/api/predict_price', methods=['POST'])
def api_predict_price():
    """Return ML-predicted unit price for a product + quantity."""
    data = request.get_json(force=True) or {}
    product_id = data.get('product_id')
    quantity   = int(data.get('quantity', 1) or 1)

    if not product_id:
        return jsonify({'error': 'product_id required'}), 400

    conn = get_db_connection()
    row  = conn.execute('SELECT name, category, price FROM products WHERE id=?',
                        (product_id,)).fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'product not found'}), 404

    base_price = float(row['price'])
    predicted  = ai_predict_price(row['category'] or '', quantity, base_price)

    return jsonify({
        'product':    row['name'],
        'category':   row['category'],
        'base_price': base_price,
        'predicted':  predicted,
        'quantity':   quantity,
        'discount_pct': round((1 - predicted / base_price) * 100, 1) if base_price else 0
    })

from admin_routes import admin_bp
app.register_blueprint(admin_bp, url_prefix='')

if __name__ == '__main__':
    print(app.url_map)
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)




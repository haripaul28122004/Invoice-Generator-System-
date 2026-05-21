"""
model.py — AI Price Prediction + Revenue Forecasting using scikit-learn
"""

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import sqlite3

# ── Category encoding map ────────────────────────────────────────────────
CATEGORY_CODES = {}   # filled by train_model()


def encode_category(cat: str) -> int:
    """Return the integer code for a category name (0 if unknown)."""
    return CATEGORY_CODES.get((cat or '').strip().lower(), 0)


# ── Trained price model + scaler (module-level singletons) ───────────────
_model  = None
_scaler = None


def _build_training_data(products: list[dict]) -> tuple:
    """
    Given a list of product dicts (keys: name, category, price),
    generate synthetic bulk-pricing rows so the model learns:
      - higher quantity  → slight discount on unit price
      - higher base price → larger absolute discount
    """
    rows = []
    for p in products:
        cat_code = encode_category(p['category'])
        base     = float(p['price'])
        for qty in [1, 2, 3, 5, 8, 10, 15, 20, 30, 50]:
            discount = min(0.15, (qty - 1) * 0.003)
            unit_price = base * (1 - discount)
            rows.append([cat_code, qty, base, unit_price])

    rows = np.array(rows, dtype=float)
    X = rows[:, :3]
    y = rows[:, 3]
    return X, y


def train_model(products: list[dict]) -> None:
    """Train the price prediction model on the given product list."""
    global _model, _scaler, CATEGORY_CODES

    if not products:
        return

    cats = sorted({(p.get('category') or 'General').strip().lower()
                   for p in products})
    CATEGORY_CODES = {cat: i + 1 for i, cat in enumerate(cats)}

    X, y = _build_training_data(products)

    _scaler = StandardScaler()
    X_scaled = _scaler.fit_transform(X)

    _model = LinearRegression()
    _model.fit(X_scaled, y)

    print(f"[AI] Model trained on {len(products)} products "
          f"({len(cats)} categories, {len(X)} samples)")


def predict_price(category: str, quantity: int, base_price: float) -> float:
    """Predict per-unit price with bulk discount. Falls back to base_price."""
    if _model is None or _scaler is None:
        return round(base_price, 2)

    cat_code = encode_category(category)
    X = np.array([[cat_code, quantity, base_price]], dtype=float)
    X_scaled = _scaler.transform(X)
    predicted = float(_model.predict(X_scaled)[0])
    predicted = max(base_price * 0.70, min(base_price * 1.10, predicted))
    return round(predicted, 2)


# ── Revenue Forecasting ───────────────────────────────────────────────────

def predict_revenue(db_path: str = 'database.db') -> dict:
    """
    Predict next-month revenue using RandomForestRegressor.
    Returns dict with keys: predicted, data_points, confidence.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # date column is stored as DD-MM-YYYY
        # extract YYYY-MM using substr for grouping
        rows = conn.execute("""
            SELECT substr(date,7,4) || '-' || substr(date,4,2) AS ym,
                   COALESCE(SUM(total), 0)                      AS revenue
            FROM   invoices
            WHERE  length(date) = 10
            GROUP  BY ym
            ORDER  BY ym ASC
        """).fetchall()
        conn.close()

        if len(rows) < 2:
            # Fallback: simple sum if < 2 months of data
            conn2 = sqlite3.connect(db_path)
            total = conn2.execute(
                "SELECT COALESCE(SUM(total),0) AS t FROM invoices"
            ).fetchone()[0]
            conn2.close()
            return {
                'predicted':    round(float(total), 2),
                'data_points':  len(rows),
                'confidence':   'low',
                'note':         'Need more months of data for better prediction'
            }

        X = np.array([[i + 1] for i in range(len(rows))], dtype=float)
        y = np.array([float(r['revenue']) for r in rows], dtype=float)

        rf = RandomForestRegressor(n_estimators=200, random_state=42)
        rf.fit(X, y)

        next_idx   = np.array([[len(rows) + 1]], dtype=float)
        predicted  = float(rf.predict(next_idx)[0])
        predicted  = max(0.0, predicted)

        # Simple R² to gauge confidence
        from sklearn.metrics import r2_score
        y_pred_train = rf.predict(X)
        r2 = r2_score(y, y_pred_train)
        confidence = 'high' if r2 > 0.85 else 'medium' if r2 > 0.5 else 'low'

        return {
            'predicted':   round(predicted, 2),
            'data_points': len(rows),
            'confidence':  confidence,
            'r2':          round(r2, 3)
        }

    except Exception as e:
        print(f'[AI] predict_revenue error: {e}')
        return {'predicted': 0.0, 'data_points': 0, 'confidence': 'low'}


def predict_best_product(db_path: str = 'database.db') -> dict | None:
    """Return the product with the highest total revenue."""
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Try invoice_items first (multi-product system)
        row = conn.execute("""
            SELECT p.name, p.category,
                   COALESCE(SUM(ii.line_total), 0) AS revenue
            FROM   products p
            LEFT   JOIN invoice_items ii ON ii.product_id = p.id
            GROUP  BY p.id
            ORDER  BY revenue DESC
            LIMIT  1
        """).fetchone()
        # Fallback: legacy invoices table
        if not row or float(row['revenue']) == 0:
            row = conn.execute("""
                SELECT product AS name, '' AS category,
                       COALESCE(SUM(total), 0) AS revenue
                FROM   invoices
                GROUP  BY product
                ORDER  BY revenue DESC
                LIMIT  1
            """).fetchone()
        conn.close()
        if row and float(row['revenue']) > 0:
            return {'name': row['name'],
                    'category': row['category'] or 'N/A',
                    'revenue': round(float(row['revenue']), 2)}
    except Exception as e:
        print(f'[AI] predict_best_product error: {e}')
    return None

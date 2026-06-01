"""Quick test: register a new customer, then try to log in."""
import importlib.util, sys

# Import app.py as a module (not __main__)
spec = importlib.util.spec_from_file_location("app_mod", "app.py")
app_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app_mod)

app = app_mod.app
app.config['TESTING'] = True

with app.test_client() as c:
    # 1. Register
    rv = c.post('/customer_register', data={
        'username': 'LoginTest4',
        'email':    'logintest4@example.com',
        'password': 'test123456',
        'confirm_password': 'test123456',
    }, follow_redirects=False)
    print(f"Register -> {rv.status_code}  Location: {rv.headers.get('Location')}")

    # 2. Login
    rv2 = c.post('/customer_login', data={
        'email':    'logintest4@example.com',
        'password': 'test123456',
    }, follow_redirects=False)
    print(f"Login    -> {rv2.status_code}  Location: {rv2.headers.get('Location')}")

    # 3. Follow login redirect to customer_dashboard
    if rv2.status_code in (301, 302):
        rv3 = c.get(rv2.headers['Location'], follow_redirects=False)
        print(f"Dashboard -> {rv3.status_code}")
        if rv3.status_code >= 400:
            print("--- RESPONSE BODY (first 3000 chars) ---")
            print(rv3.data.decode()[:3000])
    elif rv2.status_code == 200:
        body = rv2.data.decode()
        if 'Invalid' in body:
            print("LOGIN FAILED: Invalid credentials message found in response")
        else:
            print("LOGIN RENDERED login page again (no redirect)")
            print(body[:2000])

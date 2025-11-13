# Read the file
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the login_required function to remove Clerk authentication part
old_login_required = '''# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Flask session first (for existing users)
        if 'user_id' in session and session['user_id'] is not None:
            return f(*args, **kwargs)

        # Check Clerk authentication
        auth_header = request.headers.get('Authorization')
        session_token = None

        if auth_header and auth_header.startswith('Bearer '):
            session_token = auth_header[7:]


            try:
                return f(*args, **kwargs)
            except:
                pass

        return redirect(url_for('login_page'))
    return decorated_function'''

new_login_required = '''# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check Flask session (for existing users)
        if 'user_id' in session and session['user_id'] is not None:
            return f(*args, **kwargs)

        return redirect(url_for('login_page'))
    return decorated_function'''

# Replace the old function with the new one
new_content = content.replace(old_login_required, new_login_required)

# Write the updated content back to the file
with open('d:\\python\\Agentic-Ai\\Quater4\\projects\\diet-planner\\src\\diet_planner\\app.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Login required function updated to remove Clerk authentication")
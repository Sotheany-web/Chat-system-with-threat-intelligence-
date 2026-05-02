from flask import Flask, render_template, request, redirect, session
from modules.database import init_db, get_db
from modules.auth import register_user, login_user
from modules.database import get_all_users

app = Flask(__name__)
app.secret_key = "secret123"

init_db()

@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        #  INPUT VALIDATION (prevents empty crashes)
        if not username or not password:
            error = "Invalid credentials"
            return render_template('login.html', error=error)

        result = login_user(username, password)
        print("LOGIN RESULT:", result, type(result))

        if result == "success":
            session['user'] = username
            print("SESSION SET:", session.get('user'))
            return redirect('/dashboard')

        #  SECURITY FIX: always show same message
        else:
            return render_template('login.html', error=result)

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        result = register_user(username, password)

        if result == "success":
            return redirect('/login')

        # stay on same page + show error
        error = result

    return render_template('register.html', error=error)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    chat_user = request.args.get('chat_user')

    # OPTIONAL: prevent invalid users
    users = get_all_users()
    valid_users = [u[0] for u in users]

    if chat_user and chat_user not in valid_users:
        return "Invalid user", 403

    return render_template(
        'dashboard.html',
        username=session['user'],
        users=users,
        chat_user=chat_user
    )
if __name__ == '__main__':
    app.run(debug=True)
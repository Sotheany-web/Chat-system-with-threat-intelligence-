
---

````markdown id="mk9p2x"
# 🔐 Secure Chat Web Application (Flask)

A secure real-time chat-style web application built using Flask, SQLite, and Python security practices.  
The system demonstrates authentication, brute-force protection, logging, and basic attack detection mechanisms.

---

# ⚙️ How to Run

```bash
pip install flask
python app.py
````

Then open your browser:

```
http://127.0.0.1:5000
```

---

# 📁 Project Structure

```
secure_chat/

app.py
→ Main Flask application (handles routes, login, session control, dashboard)

database.db
→ SQLite database storing users and security logs

modules/
→ Backend logic modules

    database.py
    → Handles database connection and initializes tables

    auth.py
    → Authentication system (register, login, password hashing, brute-force logic)

    threat_detection.py
    → Security logging system (records login attempts and attack events)

templates/
→ HTML frontend pages

    login.html
    → User login interface

    register.html
    → User registration interface

    dashboard.html
    → Main chat/dashboard interface after login

static/
→ Frontend static assets

    assets/
        css/
        → Styling (UI design)

        js/
        → JavaScript (UI interactions and behavior)

        images/
        → UI images, avatars, icons
```

---

# 🚀 Features

## 🔐 Authentication System

* User registration with input validation
* Password hashing using SHA-256
* Secure login using parameterized SQL queries
* Session-based authentication

---

## 🛡️ Security Features

### ✔ SQL Injection Protection

* Uses parameterized queries (`?`) instead of string concatenation
* Prevents malicious SQL injection payloads

### ✔ Brute Force Protection

* Tracks failed login attempts per user
* Shows warning after multiple failed attempts
* Automatically blocks account after 5 failed attempts

### ✔ Session Management

* Flask sessions protect dashboard access
* Prevents unauthorized direct URL access

### ✔ Input Validation

* Prevents empty username/password submissions
* Basic user existence validation

---

## 📊 Threat Logging System

The system records security-related events into a `logs` table.

### Logged Events:

* LOGIN_SUCCESS
* LOGIN_FAIL
* ACCOUNT_BLOCKED

### Each log contains:

* Username
* Event type
* Description
* Timestamp

---

# 🧠 Security Summary

This application demonstrates core web security concepts:

* Authentication & Authorization
* SQL Injection prevention
* Brute-force attack mitigation
* Secure session handling
* Security event logging

---



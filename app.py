from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_required,
    current_user, login_user, logout_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# --------------------
# App Configuration
# --------------------
app = Flask(__name__)
app.secret_key = "jithu_bank_secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///bank.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --------------------
# Login Manager
# --------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

# --------------------
# Database Models
# --------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    password_hash = db.Column(db.String(255), nullable=False)
    pin_hash = db.Column(db.String(255), nullable=False)

    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def check_pin(self, pin):
        return check_password_hash(self.pin_hash, pin)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    type = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    balance_after = db.Column(db.Float, nullable=False)

    reference = db.Column(db.String(50))
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# --------------------
# User Loader
# --------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --------------------
# Routes
# --------------------
@app.route("/")
def home():
    return redirect(url_for("login"))

# --------------------
# Signup
# --------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        pin = request.form["pin"]

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Username or Email already exists", "danger")
            return redirect(url_for("signup"))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            pin_hash=generate_password_hash(pin),
            balance=0.0
        )

        db.session.add(user)
        db.session.commit()

        flash("Signup successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot_password.html")

# --------------------
# Login
# --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        pin = request.form["pin"]

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password) and user.check_pin(pin):
            login_user(user)
            flash("Login successful", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")

# --------------------
# Logout
# --------------------
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

# --------------------
# Dashboard
# --------------------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)

# --------------------
# Deposit
# --------------------
@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]
        note = request.form.get("note", "")

        if amount <= 0 or not current_user.check_pin(pin):
            flash("Invalid amount or PIN", "danger")
            return redirect(url_for("deposit"))

        current_user.balance += amount

        txn = Transaction(
            user_id=current_user.id,
            type="DEPOSIT",
            amount=amount,
            balance_after=current_user.balance,
            note=note
        )

        db.session.add(txn)
        db.session.commit()

        flash("Deposit successful", "success")
        return redirect(url_for("dashboard"))

    return render_template("deposit.html")

# --------------------
# Withdraw
# --------------------
@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    if request.method == "POST":
        amount = float(request.form["amount"])
        pin = request.form["pin"]

        if amount <= 0 or amount > current_user.balance or not current_user.check_pin(pin):
            flash("Invalid withdrawal request", "danger")
            return redirect(url_for("withdraw"))

        current_user.balance -= amount

        txn = Transaction(
            user_id=current_user.id,
            type="WITHDRAW",
            amount=-amount,
            balance_after=current_user.balance
        )

        db.session.add(txn)
        db.session.commit()

        flash("Withdrawal successful", "success")
        return redirect(url_for("dashboard"))

    return render_template("withdraw.html")

# --------------------
# Transfer
# --------------------
@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    if request.method == "POST":
        to_user = request.form["to_username"]
        amount = float(request.form["amount"])
        pin = request.form["pin"]
        note = request.form.get("note", "")

        recipient = User.query.filter_by(username=to_user).first()

        if (
            not recipient or
            recipient.id == current_user.id or
            amount <= 0 or
            amount > current_user.balance or
            not current_user.check_pin(pin)
        ):
            flash("Transfer failed", "danger")
            return redirect(url_for("transfer"))

        current_user.balance -= amount
        recipient.balance += amount

        ref = f"TXN{int(datetime.utcnow().timestamp())}"

        sender_txn = Transaction(
            user_id=current_user.id,
            type="TRANSFER_SENT",
            amount=-amount,
            balance_after=current_user.balance,
            reference=ref,
            note=note
        )

        receiver_txn = Transaction(
            user_id=recipient.id,
            type="TRANSFER_RECEIVED",
            amount=amount,
            balance_after=recipient.balance,
            reference=ref
        )

        db.session.add_all([sender_txn, receiver_txn])
        db.session.commit()

        flash("Transfer successful", "success")
        return redirect(url_for("dashboard"))

    return render_template("transfer.html")

# --------------------
# Transactions
# --------------------
@app.route("/transactions")
@login_required
def transactions():
    txns = Transaction.query.filter_by(
        user_id=current_user.id
    ).order_by(Transaction.created_at.desc()).all()

    return render_template("transactions.html", transactions=txns)

# --------------------
# Dashboard API (Charts)
# --------------------
@app.route("/api/dashboard-stats")
@login_required
def dashboard_stats():
    income = sum(t.amount for t in Transaction.query.filter_by(
        user_id=current_user.id, type="DEPOSIT"
    ))

    expense = abs(sum(t.amount for t in Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.amount < 0
    )))

    return jsonify({
        "balance": current_user.balance,
        "income": income,
        "expense": expense
    })

# --------------------
# Init DB
# --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=3000, debug=True)

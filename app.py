from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_required,
    current_user, login_user, logout_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import extract, func

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

    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# --------------------
# User Loader
# --------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))   # FIXED


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
            flash("User already exists", "danger")
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

        flash("Signup successful", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


# --------------------
# Forgot Password
# --------------------
@app.route("/forgot_password")   # FIXED NAME
def forgot_password():
    return "Forgot Password Page"


# --------------------
# Login
# --------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()

        if user and user.check_password(request.form["password"]) and user.check_pin(request.form["pin"]):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")


# --------------------
# Logout
# --------------------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# --------------------
# Dashboard
# --------------------
@app.route("/dashboard")
@login_required
def dashboard():
    txns = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc()).limit(10)

    income = sum(t.amount for t in Transaction.query.filter_by(
        user_id=current_user.id, type="DEPOSIT"
    ))

    expense = abs(sum(t.amount for t in Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.amount < 0
    )))

    return render_template(
        "dashboard.html",
        user=current_user,
        txns=txns,
        income=income,
        expense=expense
    )


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
            flash("Invalid input", "danger")
            return redirect(url_for("deposit"))

        current_user.balance += amount

        db.session.add(Transaction(
            user_id=current_user.id,
            type="DEPOSIT",
            amount=amount,
            balance_after=current_user.balance,
            note=note
        ))

        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("deposit.html", user=current_user)


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
            flash("Invalid request", "danger")
            return redirect(url_for("withdraw"))

        current_user.balance -= amount

        db.session.add(Transaction(
            user_id=current_user.id,
            type="WITHDRAW",
            amount=-amount,
            balance_after=current_user.balance
        ))

        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("withdraw.html", user=current_user)


# --------------------
# Transfer (FULL FIXED)
# --------------------
@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    if request.method == "POST":
        to_user = User.query.filter_by(username=request.form["to_username"]).first()
        amount = float(request.form["amount"])
        pin = request.form["pin"]

        if not to_user or amount <= 0 or amount > current_user.balance or not current_user.check_pin(pin):
            flash("Transfer failed", "danger")
            return redirect(url_for("transfer"))

        current_user.balance -= amount
        to_user.balance += amount

        db.session.add(Transaction(
            user_id=current_user.id,
            type="TRANSFER_SENT",
            amount=-amount,
            balance_after=current_user.balance
        ))

        db.session.add(Transaction(
            user_id=to_user.id,
            type="TRANSFER_RECEIVED",
            amount=amount,
            balance_after=to_user.balance
        ))

        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("transfer.html", user=current_user)


# --------------------
# Transactions
# --------------------
@app.route("/transactions")
@login_required
def transactions():
    txns = Transaction.query.filter_by(user_id=current_user.id)\
        .order_by(Transaction.created_at.desc()).all()

    return render_template("transactions.html", transactions=txns)


# --------------------
# API
# --------------------
@app.route("/api/dashboard-stats")
@login_required
def stats():
    income = sum(t.amount for t in Transaction.query.filter_by(
        user_id=current_user.id, type="DEPOSIT"
    ))

    expense = abs(sum(t.amount for t in Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.amount < 0
    )))

    return jsonify({"income": income, "expense": expense})


# --------------------
# EXPORT CSV
# --------------------
@app.route("/export")
@login_required
def export():
    txns = Transaction.query.filter_by(user_id=current_user.id).all()

    csv = "Date,Type,Amount,Balance\n"
    for t in txns:
        csv += f"{t.created_at},{t.type},{t.amount},{t.balance_after}\n"

    return Response(csv,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=statement.csv"})


# --------------------
# RUN
# --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=3000)
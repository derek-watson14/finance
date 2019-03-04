import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
import time
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = db.execute("SELECT symbol, shares FROM portfolio WHERE userID = :userID",
                           userID=session["user_id"])

    cash = db.execute("SELECT cash FROM users WHERE userID = :userID",
                      userID=session["user_id"])

    grand_total = cash[0]['cash']

    for row in portfolio:
        stock_info = lookup(row['symbol'])
        row['name'] = stock_info["name"]
        row['price'] = usd(stock_info["price"])
        row['total'] = usd(stock_info["price"] * row['shares'])
        grand_total += float(stock_info["price"] * row['shares'])

    return render_template("index.html", grand_total=usd(grand_total), portfolio=portfolio, cash=usd(cash[0]['cash']))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")

        if not symbol:
            return apology("symbol not found", 400)
        if not request.form.get("shares") or request.form.get("shares").isdigit() == False or int(shares) < 1:
            return apology("must input shares", 400)

        shares = int(shares)
        total = float(shares * symbol["price"])

        cash = db.execute("SELECT cash FROM users WHERE userID = :userID",
                          userID=session["user_id"])

        if total > cash[0]['cash']:
            return apology("you cannot afford that many shares", 403)

        portfolio = db.execute("SELECT shares FROM portfolio WHERE userID = :userID AND symbol = :symbol",
                               userID=session["user_id"], symbol=symbol["symbol"])

        if not portfolio:
            db.execute("INSERT INTO portfolio (userID, symbol, shares) VALUES (:userID, :symbol, :shares)",
                        userID=session["user_id"], symbol=symbol["symbol"], shares=shares)
        else:
            portfolioShares = int(portfolio[0]['shares'])
            db.execute("UPDATE portfolio SET shares = :update WHERE userID = :userID AND symbol = :symbol",
                       update=portfolioShares + shares, userID=session["user_id"], symbol=symbol["symbol"])

        db.execute("INSERT INTO ledger (userID, time, symbol, price, shares, total) VALUES (:userID, :time, :symbol, :price, :shares, :total)",
                   userID=session["user_id"], time=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=symbol["symbol"], price=symbol["price"],
                   shares=shares, total=total)

        db.execute("UPDATE users SET cash = :update WHERE userID = :userID",
                   update=cash[0]['cash'] - total,
                   userID=session["user_id"])

        flash('Bought!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    desired = request.args["username"]

    duplicates = db.execute("SELECT username FROM users WHERE username = :username",
                            username=desired)

    if len(request.args["username"]) > 0 and not duplicates:
        return jsonify(True)
    else:
        return jsonify(False)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    portfolio = db.execute("SELECT symbol, shares, price, time FROM ledger WHERE userID = :userID",
                           userID=session["user_id"])
    for row in portfolio:
        stock_info = lookup(row['symbol'])
        row['curr_price'] = stock_info["price"]

    return render_template("history.html", portfolio=portfolio)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["userID"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        if not lookup(request.form.get("symbol")):
            return apology("symbol not found", 400)

        symbol = lookup(request.form.get("symbol"))
        return render_template("quoted.html", symbol=symbol["symbol"], price=usd(symbol["price"]))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password was confrimed
        elif not request.form.get("confirmation"):
            return apology("please confirm password", 400)

        # Ensure two passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        # Add user information to "users" table in finance.db
        add_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
                              username=request.form.get("username"),
                              password=generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=4));
        if not add_user:
            return apology("username taken", 400)

        # Log user in
        session["user_id"] = add_user

        # Redirect user to login page
        flash('Registered!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        symbol = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")

        if not symbol:
            return apology("symbol not found", 400)
        if not request.form.get("shares") or request.form.get("shares").isdigit() == False or int(shares) < 1:
            return apology("must input shares", 400)

        shares = int(shares)
        total = float(shares * symbol["price"])

        cash = db.execute("SELECT cash FROM users WHERE userID = :userID",
                          userID=session["user_id"])

        portfolio = db.execute("SELECT shares FROM portfolio WHERE userID = :userID AND symbol = :symbol",
                               userID=session["user_id"], symbol=symbol["symbol"])
        portfolioShares = int(portfolio[0]['shares'])

        if not portfolio or portfolioShares < shares:
            return apology("too many shares", 400)
        else:
            db.execute("UPDATE portfolio SET shares = :update WHERE userID = :userID AND symbol = :symbol",
                       update=portfolioShares - shares, userID=session["user_id"], symbol=symbol["symbol"])
            db.execute("DELETE FROM portfolio WHERE shares = 0")

        db.execute("INSERT INTO ledger (userID, time, symbol, price, shares, total) VALUES (:userID, :time, :symbol, :price, :shares, :total)",
                   userID=session["user_id"], time=time.strftime('%Y-%m-%d %H:%M:%S'), symbol=symbol["symbol"], price=symbol["price"],
                   shares= -shares, total= -total)

        db.execute("UPDATE users SET cash = :update WHERE userID = :userID",
                   update=cash[0]['cash'] + total,
                   userID=session["user_id"])

        flash('Sold!')
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        stocks_owned = db.execute("SELECT symbol FROM portfolio WHERE userID = :userID",
                                  userID=session["user_id"])
        return render_template("sell.html", stocks_owned=stocks_owned)


@app.route("/delete", methods=["GET", "POST"])
@login_required
def delete():
    if request.method == "POST":
        db.execute("DELETE FROM users WHERE userID = :userID", userID=session["user_id"])
        db.execute("DELETE FROM portfolio WHERE userID = :userID", userID=session["user_id"])
        db.execute("DELETE FROM ledger WHERE userID = :userID", userID=session["user_id"])

        session.clear()
        flash('Account Deleted!')
        return render_template("login.html")
    else:
        return render_template("delete.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)

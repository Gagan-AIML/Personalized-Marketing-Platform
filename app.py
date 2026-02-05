from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import random
from datetime import datetime
from uuid import uuid4
from ml_model import recommend, train_and_save


app = Flask(__name__)
app.secret_key = "supersecretkey"  # replace in production

# -----------------------------
# In-Memory Storage (LOCAL ONLY)
# -----------------------------
users = {}  # {username: hashed_password}

# customers: {customer_id: {"name": str, "created_at": str}}
customers = {}

# campaigns: list of dicts
# {
#   "id": str, "customer_id": str, "product": str, "status": str,
#   "created_at": str, "open_rate": int, "click_rate": int, "conversions": int
# }
campaigns = []


# -----------------------------
# Helpers
# -----------------------------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def require_login():
    if "username" not in session:
        flash("Please login first.")
        return False
    return True

def recommend_product():
    products = ["Wireless Headphones", "Smartwatch", "Laptop", "Bluetooth Speaker"]
    return random.choice(products)

def fake_metrics():
    open_rate = random.randint(10, 90)
    click_rate = random.randint(1, max(1, open_rate))
    conversions = random.randint(0, 10)
    return open_rate, click_rate, conversions

def compute_stats(campaign_list):
    total = len(campaign_list)
    sent = sum(1 for c in campaign_list if c.get("status") == "Sent")
    avg_open = round(sum(c.get("open_rate", 0) for c in campaign_list) / total, 1) if total else 0
    avg_click = round(sum(c.get("click_rate", 0) for c in campaign_list) / total, 1) if total else 0
    total_conv = sum(c.get("conversions", 0) for c in campaign_list)
    return total, sent, avg_open, avg_click, total_conv


# -----------------------------
# Auth Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username:
            flash("Username is required.")
            return redirect(url_for("signup"))

        if username in users:
            flash("Username already exists!")
            return redirect(url_for("signup"))

        users[username] = generate_password_hash(password, method="pbkdf2:sha256")
        flash("Account created successfully! Please login.")
        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        hashed = users.get(username)
        if hashed and check_password_hash(hashed, password):
            session["username"] = username
            flash("Logged in successfully!")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.")
        return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully.")
    return redirect(url_for("login"))


# -----------------------------
# Customers
# -----------------------------
@app.route("/customers", methods=["GET", "POST"])
def customers_page():
    if not require_login():
        return redirect(url_for("login"))
    
    if request.method == "POST":
        customer_id = request.form.get("customer_id", "").strip()
        name = request.form.get("name", "").strip()
        interest = request.form.get("interest", "").strip()
        customers[customer_id] = {"name": name or "Unknown", "interest": interest, "created_at": now_str()}

        if not customer_id:
            flash("Customer ID is required.")
            return redirect(url_for("customers_page"))

        if customer_id in customers:
            flash("Customer already exists.")
            return redirect(url_for("customers_page"))

        customers[customer_id] = {"name": name or "Unknown", "created_at": now_str()}
        flash("Customer added successfully!")
        return redirect(url_for("customers_page"))

    customer_items = [{"customer_id": cid, **data} for cid, data in customers.items()]
    customer_items.sort(key=lambda x: x["customer_id"].lower())

    return render_template(
        "customers.html",
        username=session["username"],
        customers=customer_items,
        campaign_count=len(campaigns)
    )

@app.route("/customers/delete/<customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if not require_login():
        return redirect(url_for("login"))

    # delete customer
    if customer_id in customers:
        del customers[customer_id]

    # delete all campaigns for that customer
    global campaigns
    campaigns = [c for c in campaigns if c["customer_id"] != customer_id]

    flash(f"Deleted customer {customer_id} and related campaigns.")
    return redirect(url_for("customers_page"))


# -----------------------------
# Dashboard + Campaigns
# -----------------------------
@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))

    customer_items = [{"customer_id": cid, **data} for cid, data in customers.items()]
    customer_items.sort(key=lambda x: x["customer_id"].lower())

    recent_campaigns = list(reversed(campaigns))

    return render_template(
        "dashboard.html",
        username=session["username"],
        customers=customer_items,
        campaigns=recent_campaigns
    )

@app.route('/launch_campaign', methods=['POST'])
def launch_campaign():
    if 'username' not in session:
        flash("Please login first")
        return redirect(url_for('login'))

    customer_id = request.form.get("customer_id", "").strip()
    product = request.form.get("product", "").strip()

    if customer_id not in customers:
        flash("Customer not found.")
        return redirect(url_for("customers_page"))

    # --- AI Recommendation ---
    if product == "AI Recommended":
        predicted = recommend(customers, campaigns, customer_id)
        print(f"🤖 ML predicted product for {customer_id}: {predicted}")
        product = predicted

    # --- Generate engagement metrics ---
    open_rate, click_rate, conversions = fake_metrics()

    # --- Save campaign ---
    campaigns.append({
        "id": str(uuid4()),
        "customer_id": customer_id,
        "product": product,
        "status": "Sent",
        "created_at": now_str(),
        "open_rate": open_rate,
        "click_rate": click_rate,
        "conversions": conversions
    })

    # --- TRAIN MODEL HERE ---
    result = train_and_save(customers, campaigns)
    if result:
        print("✅ ML model trained and saved")
    else:
        print("⚠️ Not enough data to train ML model yet")

    flash(f"Campaign launched for {customer_id}")
    return redirect(url_for('dashboard'))


@app.route("/campaigns/delete/<campaign_id>", methods=["POST"])
def delete_campaign(campaign_id):
    if not require_login():
        return redirect(url_for("login"))

    global campaigns
    before = len(campaigns)
    campaigns = [c for c in campaigns if c["id"] != campaign_id]
    after = len(campaigns)

    if after < before:
        flash("Campaign deleted.")
    else:
        flash("Campaign not found.")

    # return to page user came from (dashboard or analytics)
    next_page = request.form.get("next", "dashboard")
    if next_page == "analytics":
        # preserve filters/search when possible
        customer_filter = request.form.get("customer", "")
        q = request.form.get("q", "")
        return redirect(url_for("analytics", customer=customer_filter, q=q))

    return redirect(url_for("dashboard"))


# -----------------------------
# Analytics (Filter + Search)
# -----------------------------
@app.route("/analytics")
def analytics():
    if not require_login():
        return redirect(url_for("login"))

    # dropdown of customers
    customer_items = [{"customer_id": cid, **data} for cid, data in customers.items()]
    customer_items.sort(key=lambda x: x["customer_id"].lower())

    # filters from query params
    customer_filter = request.args.get("customer", "").strip()
    q = request.args.get("q", "").strip().lower()

    filtered = campaigns[:]

    # filter by customer
    if customer_filter:
        filtered = [c for c in filtered if c["customer_id"] == customer_filter]

    # search across customer_id/product/status
    if q:
        def match(c):
            return (
                q in c["customer_id"].lower()
                or q in c["product"].lower()
                or q in c["status"].lower()
                or q in c.get("created_at", "").lower()
            )
        filtered = [c for c in filtered if match(c)]

    # newest first
    filtered_recent = list(reversed(filtered))

    total, sent, avg_open, avg_click, total_conv = compute_stats(filtered)

    return render_template(
        "analytics.html",
        username=session["username"],
        customers=customer_items,
        campaigns=filtered_recent,
        total_campaigns=total,
        sent_campaigns=sent,
        avg_open=avg_open,
        avg_click=avg_click,
        total_conversions=total_conv,
        customer_filter=customer_filter,
        q=q
    )


if __name__ == "__main__":
    app.run(debug=True)

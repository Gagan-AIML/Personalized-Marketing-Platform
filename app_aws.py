# app_aws.py
# AWS-compatible version of your AI-Driven Personalized Marketing Platform
# Uses DynamoDB for Users/Customers/Campaigns and SNS for notifications.
# Keeps your current logic (customer_id stays as-is).

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os
import boto3
from botocore.exceptions import ClientError
from uuid import uuid4
from datetime import datetime
import random

# OPTIONAL (if you already have these files and want ML on AWS too):
# from ml_model import recommend, train_and_save

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key_change_me")

# -----------------------------
# AWS Configuration
# -----------------------------
REGION = os.environ.get("AWS_REGION", "us-east-1")

USERS_TABLE_NAME = os.environ.get("USERS_TABLE", "MarketingUsers")
CUSTOMERS_TABLE_NAME = os.environ.get("CUSTOMERS_TABLE", "MarketingCustomers")
CAMPAIGNS_TABLE_NAME = os.environ.get("CAMPAIGNS_TABLE", "MarketingCampaigns")

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")  # optional (leave empty to disable)

dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

users_table = dynamodb.Table(USERS_TABLE_NAME)
customers_table = dynamodb.Table(CUSTOMERS_TABLE_NAME)
campaigns_table = dynamodb.Table(CAMPAIGNS_TABLE_NAME)


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


def send_notification(subject: str, message: str):
    """Publish to SNS topic (optional)."""
    if not SNS_TOPIC_ARN:
        return
    try:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    except ClientError as e:
        print(f"SNS publish error: {e}")


def fake_metrics():
    """Temporary engagement metrics (until you wire real tracking)."""
    open_rate = random.randint(10, 90)
    click_rate = random.randint(1, max(1, open_rate))
    conversions = random.randint(0, 10)
    return int(open_rate), int(click_rate), int(conversions)


def compute_stats(campaign_list):
    total = len(campaign_list)
    sent = sum(1 for c in campaign_list if c.get("status") == "Sent")
    avg_open = round(sum(int(c.get("open_rate", 0)) for c in campaign_list) / total, 1) if total else 0
    avg_click = round(sum(int(c.get("click_rate", 0)) for c in campaign_list) / total, 1) if total else 0
    total_conv = sum(int(c.get("conversions", 0)) for c in campaign_list)
    return total, sent, avg_open, avg_click, total_conv


# -----------------------------
# DynamoDB CRUD
# -----------------------------
def db_get_user(username: str):
    res = users_table.get_item(Key={"username": username})
    return res.get("Item")


def db_create_user(username: str, password_hash: str):
    users_table.put_item(Item={"username": username, "password_hash": password_hash})


def db_list_customers():
    res = customers_table.scan()
    items = res.get("Items", [])
    items.sort(key=lambda x: x.get("customer_id", "").lower())
    return items


def db_customer_exists(customer_id: str) -> bool:
    res = customers_table.get_item(Key={"customer_id": customer_id})
    return "Item" in res


def db_add_customer(customer_id: str, name: str, interest: str):
    customers_table.put_item(Item={
        "customer_id": customer_id,
        "name": name or "Unknown",
        "interest": interest or "unknown",
        "created_at": now_str()
    })


def db_delete_customer(customer_id: str):
    customers_table.delete_item(Key={"customer_id": customer_id})


def db_list_campaigns():
    res = campaigns_table.scan()
    items = res.get("Items", [])
    # newest first
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items


def db_add_campaign(item: dict):
    campaigns_table.put_item(Item=item)


def db_delete_campaign(campaign_id: str):
    campaigns_table.delete_item(Key={"campaign_id": campaign_id})


def db_delete_campaigns_for_customer(customer_id: str):
    """
    For small projects, scan+delete is OK.
    For production, add a GSI on customer_id and query instead.
    """
    res = campaigns_table.scan()
    items = res.get("Items", [])
    for c in items:
        if c.get("customer_id") == customer_id and c.get("campaign_id"):
            campaigns_table.delete_item(Key={"campaign_id": c["campaign_id"]})


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username:
            flash("Username is required.")
            return redirect(url_for("signup"))

        if db_get_user(username):
            flash("Username already exists!")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        db_create_user(username, password_hash)

        send_notification("New User Signup", f"User {username} signed up.")
        flash("Account created successfully! Please login.")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = db_get_user(username)
        if user and check_password_hash(user["password_hash"], password):
            session["username"] = username
            send_notification("User Login", f"User {username} logged in.")
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


@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))

    customers = db_list_customers()
    campaigns = db_list_campaigns()

    return render_template(
        "dashboard.html",
        username=session["username"],
        customers=customers,
        campaigns=campaigns
    )


@app.route("/customers", methods=["GET", "POST"])
def customers_page():
    if not require_login():
        return redirect(url_for("login"))

    if request.method == "POST":
        customer_id = request.form.get("customer_id", "").strip()
        name = request.form.get("name", "").strip()
        interest = request.form.get("interest", "").strip()

        if not customer_id:
            flash("Customer ID is required.")
            return redirect(url_for("customers_page"))

        if db_customer_exists(customer_id):
            flash("Customer already exists.")
            return redirect(url_for("customers_page"))

        db_add_customer(customer_id, name, interest)
        send_notification("Customer Added", f"Customer {customer_id} added.")
        flash("Customer added successfully!")
        return redirect(url_for("customers_page"))

    customers = db_list_customers()
    campaign_count = len(db_list_campaigns())

    return render_template(
        "customers.html",
        username=session["username"],
        customers=customers,
        campaign_count=campaign_count
    )


@app.route("/customers/delete/<customer_id>", methods=["POST"])
def delete_customer(customer_id):
    if not require_login():
        return redirect(url_for("login"))

    if db_customer_exists(customer_id):
        db_delete_customer(customer_id)
        db_delete_campaigns_for_customer(customer_id)
        send_notification("Customer Deleted", f"Customer {customer_id} deleted (campaigns removed).")
        flash(f"Deleted customer {customer_id} and related campaigns.")
    else:
        flash("Customer not found.")

    return redirect(url_for("customers_page"))


@app.route("/launch_campaign", methods=["POST"])
def launch_campaign():
    if not require_login():
        return redirect(url_for("login"))

    customer_id = request.form.get("customer_id", "").strip()
    product = request.form.get("product", "").strip()

    if not customer_id:
        flash("Please select a customer.")
        return redirect(url_for("dashboard"))

    if not db_customer_exists(customer_id):
        flash("Customer not found. Add customer first.")
        return redirect(url_for("customers_page"))

    if not product:
        flash("Please select a product.")
        return redirect(url_for("dashboard"))

    # --- AI Recommendation ---
    # If you want to use your ML model on AWS:
    # if product == "AI Recommended":
    #     customers = {c["customer_id"]: c for c in db_list_customers()}
    #     campaigns = db_list_campaigns()
    #     product = recommend(customers, campaigns, customer_id)

    # If ML not enabled on AWS yet, keep a safe deterministic fallback:
    if product == "AI Recommended":
        # You can change this to any default or keep your local ML later.
        product = "Wireless Headphones"

    open_rate, click_rate, conversions = fake_metrics()

    campaign_item = {
        "campaign_id": str(uuid4()),
        "customer_id": customer_id,
        "product": product,
        "status": "Sent",
        "created_at": now_str(),
        "open_rate": open_rate,
        "click_rate": click_rate,
        "conversions": conversions
    }

    db_add_campaign(campaign_item)

    send_notification("Campaign Launched", f"Campaign launched for {customer_id}: {product}")
    flash(f"Campaign launched for {customer_id}")
    return redirect(url_for("dashboard"))


@app.route("/campaigns/delete/<campaign_id>", methods=["POST"])
def delete_campaign(campaign_id):
    if not require_login():
        return redirect(url_for("login"))

    db_delete_campaign(campaign_id)
    send_notification("Campaign Deleted", f"Campaign deleted: {campaign_id}")
    flash("Campaign deleted.")

    next_page = request.form.get("next", "dashboard")
    if next_page == "analytics":
        customer_filter = request.form.get("customer", "")
        q = request.form.get("q", "")
        return redirect(url_for("analytics", customer=customer_filter, q=q))
    return redirect(url_for("dashboard"))


@app.route("/analytics")
def analytics():
    if not require_login():
        return redirect(url_for("login"))

    customers = db_list_customers()
    all_campaigns = db_list_campaigns()

    customer_filter = request.args.get("customer", "").strip()
    q = request.args.get("q", "").strip().lower()

    filtered = all_campaigns

    if customer_filter:
        filtered = [c for c in filtered if c.get("customer_id") == customer_filter]

    if q:
        def match(c):
            return (
                q in str(c.get("customer_id", "")).lower()
                or q in str(c.get("product", "")).lower()
                or q in str(c.get("status", "")).lower()
                or q in str(c.get("created_at", "")).lower()
            )
        filtered = [c for c in filtered if match(c)]

    total, sent, avg_open, avg_click, total_conv = compute_stats(filtered)

    return render_template(
        "analytics.html",
        username=session["username"],
        customers=customers,
        campaigns=filtered,
        total_campaigns=total,
        sent_campaigns=sent,
        avg_open=avg_open,
        avg_click=avg_click,
        total_conversions=total_conv,
        customer_filter=customer_filter,
        q=q
    )


if __name__ == "__main__":
    # Works on EC2 / Elastic Beanstalk
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

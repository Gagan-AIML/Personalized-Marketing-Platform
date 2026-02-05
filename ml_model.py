import os
import pickle
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

MODEL_PATH = "recommender.pkl"

PRODUCTS = ["Wireless Headphones", "Smartwatch", "Laptop", "Bluetooth Speaker"]

def build_training_data(customers, campaigns):
    """
    Build X (features) and y (product) from your stored customers + campaign results.
    Uses customer interest + engagement features.
    """
    X = []
    y = []

    # Only learn from campaigns that have engagement outcome
    for c in campaigns:
        cust_id = c["customer_id"]
        cust = customers.get(cust_id, {})

        # Interest feature (important!)
        interest = cust.get("interest", "unknown")

        # Engagement features
        open_rate = c.get("open_rate", 0)
        click_rate = c.get("click_rate", 0)
        conversions = c.get("conversions", 0)

        features = {
            "interest": interest,
            "open_rate": open_rate,
            "click_rate": click_rate,
            "conversions": conversions,
        }

        X.append(features)
        y.append(c["product"])

    return X, y


def train_and_save(customers, campaigns):
    X, y = build_training_data(customers, campaigns)

    # If not enough data, don't train
    if len(X) < 5:
        return None

    vec = DictVectorizer(sparse=False)
    X_vec = vec.fit_transform(X)

    clf = LogisticRegression(max_iter=500)
    clf.fit(X_vec, y)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump((vec, clf), f)

    return (vec, clf)


def load_model():
    if not os.path.exists(MODEL_PATH):
        return None
    with open(MODEL_PATH, "rb") as f:
        vec, clf = pickle.load(f)
    return vec, clf


def recommend(customers, campaigns, customer_id):
    """
    Recommend best product for customer_id using trained model.
    If no model available, fallback to smart rule-based default.
    """
    model = load_model()
    cust = customers.get(customer_id, {})
    interest = cust.get("interest", "unknown")

    # fallback if no model trained yet
    if model is None:
        # Smart fallback (not random)
        mapping = {
            "electronics": "Wireless Headphones",
            "gadgets": "Smartwatch",
            "computers": "Laptop",
            "music": "Bluetooth Speaker",
        }
        return mapping.get(interest.lower(), "Wireless Headphones")

    vec, clf = model

    # Build feature from customer's recent engagement
    recent = [c for c in campaigns if c["customer_id"] == customer_id]
    if recent:
        last = recent[-1]
        open_rate = last.get("open_rate", 0)
        click_rate = last.get("click_rate", 0)
        conversions = last.get("conversions", 0)
    else:
        open_rate = click_rate = conversions = 0

    features = [{
        "interest": interest,
        "open_rate": open_rate,
        "click_rate": click_rate,
        "conversions": conversions,
    }]

    X_vec = vec.transform(features)
    pred = clf.predict(X_vec)[0]
    return pred

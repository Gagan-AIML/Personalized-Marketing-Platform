import os
import boto3
from moto import mock_aws

# -----------------------------
# Mock AWS Credentials (required by boto3 even though Moto intercepts)
# -----------------------------
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_REGION"] = "us-east-1"

# (Optional) Match table env vars used by app_aws.py (defaults are same)
os.environ["USERS_TABLE"] = "MarketingUsers"
os.environ["CUSTOMERS_TABLE"] = "MarketingCustomers"
os.environ["CAMPAIGNS_TABLE"] = "MarketingCampaigns"

# Start Moto mock BEFORE importing app_aws
mock = mock_aws()
mock.start()

# Import your AWS Flask app after mock setup
import app_aws
from app_aws import app


def setup_infrastructure():
    print(">>> Creating Mocked AWS Resources (DynamoDB Tables & SNS Topic)...")

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    sns = boto3.client("sns", region_name="us-east-1")

    # -----------------------------
    # Create DynamoDB tables expected by app_aws.py
    # -----------------------------
    # Table: MarketingUsers (PK: username)
    dynamodb.create_table(
        TableName="MarketingUsers",
        KeySchema=[{"AttributeName": "username", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "username", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Table: MarketingCustomers (PK: customer_id)
    dynamodb.create_table(
        TableName="MarketingCustomers",
        KeySchema=[{"AttributeName": "customer_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "customer_id", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # Table: MarketingCampaigns (PK: campaign_id)
    dynamodb.create_table(
        TableName="MarketingCampaigns",
        KeySchema=[{"AttributeName": "campaign_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "campaign_id", "AttributeType": "S"}],
        ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    )

    # -----------------------------
    # Create SNS topic and inject ARN into app_aws
    # -----------------------------
    topic_resp = sns.create_topic(Name="ai_marketing_topic")
    topic_arn = topic_resp["TopicArn"]

    # app_aws.py reads SNS_TOPIC_ARN from module variable (set it here)
    app_aws.SNS_TOPIC_ARN = topic_arn

    print(">>> Mock Environment Ready.")
    print(f">>> SNS Topic ARN: {topic_arn}")


if __name__ == "__main__":
    try:
        setup_infrastructure()
        print("\n>>> Starting Flask Server at http://localhost:5000")
        print(">>> Stop with CTRL+C. Mock data will be lost on exit.")
        # IMPORTANT: use_reloader=False prevents spawning a new process and losing mock state
        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
    finally:
        mock.stop()

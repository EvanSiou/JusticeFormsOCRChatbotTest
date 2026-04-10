"""
Create DynamoDB tables for the OCR Testing App.
Run once to provision all required tables.

Usage:
    python setup_dynamodb.py [--prefix ocr-testing] [--region us-west-2]
"""
import argparse
import boto3


def create_table(client, table_name, key_schema, attribute_defs, gsis=None):
    try:
        kwargs = {
            "TableName": table_name,
            "KeySchema": key_schema,
            "AttributeDefinitions": attribute_defs,
            "BillingMode": "PAY_PER_REQUEST",
        }
        if gsis:
            kwargs["GlobalSecondaryIndexes"] = gsis
        client.create_table(**kwargs)
        print(f"  Created: {table_name}")
    except client.exceptions.ResourceInUseException:
        print(f"  Exists:  {table_name}")


def main():
    parser = argparse.ArgumentParser(description="Create DynamoDB tables")
    parser.add_argument("--prefix", default="ocr-testing", help="Table name prefix")
    parser.add_argument("--region", default="us-west-2", help="AWS region")
    args = parser.parse_args()

    client = boto3.client("dynamodb", region_name=args.region)
    prefix = args.prefix

    print(f"Creating DynamoDB tables with prefix '{prefix}' in {args.region}...\n")

    create_table(client, f"{prefix}-users",
        key_schema=[{"AttributeName": "id", "KeyType": "HASH"}],
        attribute_defs=[
            {"AttributeName": "id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        gsis=[{
            "IndexName": "email-index",
            "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )

    for table in ["forms", "batches", "test-runs", "batch-jobs", "prompts", "reference-templates"]:
        create_table(client, f"{prefix}-{table}",
            key_schema=[{"AttributeName": "id", "KeyType": "HASH"}],
            attribute_defs=[{"AttributeName": "id", "AttributeType": "S"}],
        )

    create_table(client, f"{prefix}-results",
        key_schema=[{"AttributeName": "id", "KeyType": "HASH"}],
        attribute_defs=[
            {"AttributeName": "id", "AttributeType": "S"},
            {"AttributeName": "test_run_id", "AttributeType": "S"},
        ],
        gsis=[{
            "IndexName": "test_run_id-index",
            "KeySchema": [{"AttributeName": "test_run_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
        }],
    )

    create_table(client, f"{prefix}-layout-cache",
        key_schema=[{"AttributeName": "cache_key", "KeyType": "HASH"}],
        attribute_defs=[{"AttributeName": "cache_key", "AttributeType": "S"}],
    )

    print(f"\nDone! All 9 tables provisioned.")
    print(f"  DYNAMODB_TABLE_PREFIX={prefix}")
    print(f"  AWS_DEFAULT_REGION={args.region}")


if __name__ == "__main__":
    main()

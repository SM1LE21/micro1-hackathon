"""Object storage for civicbeam."""

import boto3

from config import AWS_REGION

BUCKET = "uploads"
s3 = boto3.client("s3", region_name=AWS_REGION)


def document_key(user_id, document_id):
    return f"docs/{user_id}/{document_id}.pdf"


def upload_document(user_id, document_id, data):
    key = document_key(user_id, document_id)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=data,
        ServerSideEncryption="AES256",
    )
    return key

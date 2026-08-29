"""Object storage for snapledger."""

import boto3

from config import AWS_REGION

BUCKET = "uploads"
s3 = boto3.client("s3", region_name=AWS_REGION)


def avatar_key(user_id):
    return f"avatars/{user_id}.jpg"


def upload_avatar(user_id, data):
    key = avatar_key(user_id)
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=data,
        ServerSideEncryption="AES256",
    )
    return key


def delete_avatar(user_id):
    s3.delete_object(Bucket=BUCKET, Key=avatar_key(user_id))

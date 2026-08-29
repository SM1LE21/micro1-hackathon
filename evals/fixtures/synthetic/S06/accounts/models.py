"""Data models for the accounts app.

One class per table. Every model names its table explicitly.
"""

from django.db import models


class Account(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(max_length=255)
    full_name = models.CharField(max_length=255)
    avatar = models.ImageField(upload_to="account/avatars/")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_account"


class Comment(models.Model):
    id = models.AutoField(primary_key=True)
    body = models.TextField()
    posted_at = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey(Account, on_delete=models.DB_CASCADE)

    class Meta:
        db_table = "accounts_comment"


class Address(models.Model):
    id = models.AutoField(primary_key=True)
    street = models.CharField(max_length=255)
    postcode = models.CharField(max_length=255)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "accounts_address"

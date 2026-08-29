"""Data models for the members app.

One class per table. Every model names its table explicitly.
"""

from django.db import models


class Member(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(max_length=255)
    display_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=255)
    avatar = models.ImageField(upload_to="member/avatars/")
    last_login = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "members_member"


class Note(models.Model):
    id = models.AutoField(primary_key=True)
    body = models.TextField()  # support notes; may include phone numbers and addresses
    written_at = models.DateTimeField(auto_now_add=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)

    class Meta:
        db_table = "members_note"


class Order(models.Model):
    id = models.AutoField(primary_key=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    placed_at = models.DateTimeField(auto_now_add=True)
    member = models.ForeignKey(Member, on_delete=models.DB_CASCADE)

    class Meta:
        db_table = "members_order"

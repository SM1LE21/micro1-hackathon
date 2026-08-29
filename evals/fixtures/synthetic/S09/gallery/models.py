"""Data models for the gallery app.

One class per table. Every model names its table explicitly.
"""

from django.db import models


class Account(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.EmailField(max_length=255)
    full_name = models.CharField(max_length=255)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gallery_account"


class Photo(models.Model):
    id = models.AutoField(primary_key=True)
    image = models.ImageField(upload_to="photo/images/")
    caption = models.CharField(max_length=255)
    taken_at = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "gallery_photo"


class Comment(models.Model):
    id = models.AutoField(primary_key=True)
    body = models.TextField()
    posted_at = models.DateTimeField(auto_now_add=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)

    class Meta:
        db_table = "gallery_comment"

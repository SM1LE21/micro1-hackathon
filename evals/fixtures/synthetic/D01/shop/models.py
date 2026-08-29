"""Data models for the shop app.

One class per table. Every model names its table explicitly.
"""

from django.db import models


class Product(models.Model):
    id = models.AutoField(primary_key=True)
    sku = models.CharField(max_length=255)
    title = models.CharField(max_length=255)

    class Meta:
        db_table = "shop_product"

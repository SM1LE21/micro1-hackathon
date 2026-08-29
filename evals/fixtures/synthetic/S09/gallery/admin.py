"""Admin registrations for the gallery app."""

from django.contrib import admin

from .models import Account, Photo

admin.site.register(Account)
admin.site.register(Photo)

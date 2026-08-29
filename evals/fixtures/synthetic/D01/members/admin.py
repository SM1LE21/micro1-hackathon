"""Admin registrations for the members app."""

from django.contrib import admin

from .models import Member

admin.site.register(Member)

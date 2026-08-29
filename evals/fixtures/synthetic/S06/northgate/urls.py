"""URL routing for northgate."""

from django.contrib import admin
from django.urls import path

from accounts import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/<int:pk>/delete/", views.delete_account, name="delete_account"),
    path("accounts/<int:pk>/profile/", views.profile, name="profile"),
]

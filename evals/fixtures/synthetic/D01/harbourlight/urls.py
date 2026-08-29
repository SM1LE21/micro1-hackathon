"""URL routing for harbourlight."""

from django.contrib import admin
from django.urls import path

from members import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("members/<int:pk>/delete/", views.delete_account, name="delete_account"),
    path("members/<int:pk>/profile/", views.profile, name="profile"),
    path("members/<int:pk>/login/", views.login, name="login"),
]

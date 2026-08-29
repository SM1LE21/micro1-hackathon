"""URL routing for slatecove."""

from django.contrib import admin
from django.urls import path

from gallery import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("gallery/<int:pk>/delete/", views.delete_account, name="delete_account"),
    path("gallery/<int:pk>/gallery_index/", views.gallery_index, name="gallery_index"),
]

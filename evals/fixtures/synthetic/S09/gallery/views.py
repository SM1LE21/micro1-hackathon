"""Views for the gallery app."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Account, Photo


def delete_account(request, pk):
    """Delete the account, its photos and its comments."""
    account = get_object_or_404(Account, pk=pk)
    account.delete()
    return JsonResponse({"deleted": True})


def gallery_index(request, pk):
    photo = Photo.objects.filter(account_id=pk).first()
    return JsonResponse({"caption": photo.caption})

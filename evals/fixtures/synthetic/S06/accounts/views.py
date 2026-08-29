"""Views for the accounts app."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Account


def delete_account(request, pk):
    """Delete the account. Comments and addresses go with it."""
    account = get_object_or_404(Account, pk=pk)
    account.delete()
    return JsonResponse({"deleted": True})


def profile(request, pk):
    account = get_object_or_404(Account, pk=pk)
    return JsonResponse({"email": account.email, "full_name": account.full_name})

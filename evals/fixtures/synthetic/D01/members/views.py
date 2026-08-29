"""Views for the members app."""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from .models import Member


def delete_account(request, pk):
    """Remove the member and everything attached to it."""
    member = get_object_or_404(Member, pk=pk)
    member.delete()
    return JsonResponse({"deleted": True})


def profile(request, pk):
    member = get_object_or_404(Member, pk=pk)
    return JsonResponse({"email": member.email, "display_name": member.display_name})


def login(request, pk):
    member = get_object_or_404(Member, pk=pk)
    return JsonResponse({"email": member.email})

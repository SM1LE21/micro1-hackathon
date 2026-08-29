"""Signal receivers for the accounts app."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Account


@receiver(post_delete, sender=Account)
def delete_avatar_file(sender, instance, **kwargs):
    instance.avatar.delete(save=False)

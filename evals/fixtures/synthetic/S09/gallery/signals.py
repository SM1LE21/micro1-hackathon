"""Signal receivers for the gallery app."""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Comment


@receiver(post_delete, sender=Comment)
def delete_attached_image(sender, instance, **kwargs):
    instance.image.delete(save=False)

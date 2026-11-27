from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Notice

@receiver(post_save, sender=Notice)
def push_notice_to_websocket(sender, instance, created, **kwargs):
    if not created:
        return
    layer = get_channel_layer()
    if layer is None:
        return
    payload = {
        "type": "notification",
        "id": instance.pk,
        "message": instance.message,
        "created_at": instance.created_at.isoformat(),
    }
    try:
        async_to_sync(layer.group_send)(
            f"user_{instance.recipient_id}",
            {"type": "notification.message", "payload": payload},
        )
    except Exception:
        # A temporary Redis outage must not prevent saving the database notice.
        return

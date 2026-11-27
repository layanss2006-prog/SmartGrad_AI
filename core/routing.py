from django.urls import path
from .consumers import GroupChatConsumer, UserNotificationConsumer

websocket_urlpatterns = [
    path("ws/notifications/", UserNotificationConsumer.as_asgi()),
    path("ws/groups/<int:group_id>/chat/", GroupChatConsumer.as_asgi()),
]

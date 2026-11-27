from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import ChatMessage, StudyGroup
from .permissions import can_access_group

class UserNotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"user_{user.pk}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def notification_message(self, event):
        await self.send_json(event["payload"])


class GroupChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        self.group_id = self.scope["url_route"]["kwargs"]["group_id"]
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self.can_access_chat(user.pk, self.group_id):
            await self.close(code=4403)
            return

        self.group_name = f"chat_{self.group_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, "group_name", None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        message = content.get("content") if isinstance(content, dict) else None
        if not isinstance(message, str) or not message.strip() or len(message.strip()) > 2000:
            await self.send_json({"type": "error", "code": "invalid_message"})
            return

        payload = await self.save_message(
            self.group_id,
            self.scope["user"].pk,
            message.strip(),
        )
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "chat.message", "payload": payload},
        )

    async def chat_message(self, event):
        await self.send_json({"type": "message", **event["payload"]})

    @database_sync_to_async
    def can_access_chat(self, user_id, group_id):
        group = StudyGroup.objects.filter(pk=group_id).first()
        if not group:
            return False
        user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
        return bool(user and can_access_group(user, group))

    @database_sync_to_async
    def save_message(self, group_id, user_id, content):
        message = ChatMessage.objects.create(
            group_id=group_id,
            sender_id=user_id,
            content=content,
        )
        return {
            "id": message.pk,
            "content": message.content,
            "sender": message.sender.get_full_name() or message.sender.username,
            "sender_id": message.sender_id,
            "created_at": timezone.localtime(message.created_at).isoformat(),
        }

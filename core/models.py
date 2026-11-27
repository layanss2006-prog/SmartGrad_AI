import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

class User(AbstractUser):
    ROLE_CHOICES = [("student", "طالب"), ("teacher", "مشرف / معلم")]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="student")
    university_id = models.CharField(max_length=30, unique=True, null=True, blank=True)
    major = models.CharField(max_length=120, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

class AISettings(models.Model):
    api_key = models.CharField(max_length=255, blank=True, default="")
    model_name = models.CharField(max_length=80, default="gpt-4o-mini")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI Settings"
        verbose_name_plural = "AI Settings"

    def __str__(self):
        return self.model_name or "OpenAI"


class StudyGroup(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="led_groups")
    teachers = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="supervised_groups")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="study_groups")
    invite_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class JoinRequest(models.Model):
    STATUS = [("pending", "قيد الانتظار"), ("accepted", "مقبول"), ("rejected", "مرفوض")]
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="join_requests")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("group", "student")

class Task(models.Model):
    STATUS = [("todo", "لم تبدأ"), ("doing", "قيد التنفيذ"), ("done", "مكتملة")]
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="tasks")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="todo")
    is_current = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "created_at"]

class Submission(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="submissions")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    file = models.FileField(upload_to="submissions/")
    note = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Notice(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notices")
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class ChatMessage(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name="chat_messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_messages")
    content = models.CharField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["group", "created_at"])]

    def __str__(self):
        return f"{self.sender} · {self.group} · {self.created_at:%Y-%m-%d %H:%M}"

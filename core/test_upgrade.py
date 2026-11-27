from datetime import date, timedelta
from io import BytesIO
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .ai import build_group_analytics, build_student_productivity, build_deadline_alerts, generate_group_insight, generate_group_plan
from .models import StudyGroup, Task, Notice, Submission, AISettings, ChatMessage
from .forms import TaskForm
from .routing import websocket_urlpatterns
from .validators import validate_submission_file
from django.core.exceptions import ValidationError

User = get_user_model()


class SmartGradPermissionTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user(
            username="leader", password="StrongPass!234", role="student"
        )
        self.member = User.objects.create_user(
            username="member", password="StrongPass!234", role="student"
        )
        self.outsider = User.objects.create_user(
            username="outsider", password="StrongPass!234", role="student"
        )
        self.teacher = User.objects.create_user(
            username="teacher", password="StrongPass!234", role="teacher"
        )
        self.group = StudyGroup.objects.create(name="Research Team", leader=self.leader)
        self.group.members.add(self.leader, self.member)
        self.task = Task.objects.create(
            group=self.group, assigned_to=self.member, title="Research",
            created_by=self.leader, is_current=True
        )

    def test_task_deadline_cannot_precede_start_date(self):
        form = TaskForm(data={
            "title": "assignment",
            "description": "",
            "start_date": "2026-12-10",
            "due_date": "2026-12-05",
            "is_current": False,
        })

        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())

    def test_teacher_registration_logs_in_immediately(self):
        response = self.client.post(reverse("register"), {
            "first_name": "Teacher",
            "email": "pending-teacher@example.com",
            "university_id": "T100", "major": "IT", "role": "teacher",
            "password1": "StrongPass!234", "password2": "StrongPass!234",
        })
        teacher = User.objects.get(email="pending-teacher@example.com")
        self.assertTrue(teacher.username.startswith("smartgrad-"))
        self.assertEqual(teacher.role, "teacher")
        self.assertTrue(teacher.is_active)
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_register_form_displays_both_account_types(self):
        from .forms import RegisterForm
        form = RegisterForm()
        self.assertNotIn("username", form.fields)
        self.assertEqual([choice[0] for choice in form.fields["role"].choices], ["student", "teacher"])

    def test_outsider_cannot_open_group(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("group_detail", args=[self.group.pk]))
        self.assertEqual(response.status_code, 403)

    def test_group_chat_history_is_visible_to_group_members(self):
        ChatMessage.objects.create(group=self.group, sender=self.member, content="Team update")
        self.client.force_login(self.member)

        response = self.client.get(reverse("group_detail", args=[self.group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "محادثة الطلاب والمشرفين")
        self.assertContains(response, "Team update")

    def test_outsider_cannot_read_group_chat_history(self):
        ChatMessage.objects.create(group=self.group, sender=self.member, content="Private group update")
        self.client.force_login(self.outsider)

        response = self.client.get(reverse("group_detail", args=[self.group.pk]))

        self.assertEqual(response.status_code, 403)

    def test_unassigned_teacher_cannot_create_task_in_another_group(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_task", args=[self.group.pk]))
        self.assertEqual(response.status_code, 403)

    def test_group_teacher_can_create_task(self):
        self.group.teachers.add(self.teacher)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_task", args=[self.group.pk]))
        self.assertEqual(response.status_code, 200)

    def test_group_manager_sees_copy_invite_link_button(self):
        self.client.force_login(self.leader)

        response = self.client.get(reverse("group_detail", args=[self.group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="copy-invite"', html=False)
        self.assertContains(response, 'id="invite-link"', html=False)
        self.assertContains(response, "نسخ الرابط")

    def test_teacher_can_manage_ai_settings(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse("ai_settings"), {
            "api_key": "sk-test-123",
            "model_name": "gpt-4o-mini",
        })
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(AISettings.objects.get(pk=1).api_key, "sk-test-123")

    def test_group_leader_can_generate_ai_task_plan(self):
        self.client.force_login(self.leader)
        before = Task.objects.filter(group=self.group).count()
        response = self.client.post(reverse("create_ai_plan", args=[self.group.pk]))
        self.assertEqual(response.status_code, 302)
        created = Task.objects.filter(group=self.group).count()
        self.assertGreater(created, before)
        self.assertTrue(Task.objects.filter(group=self.group, title__icontains="Requirements review").exists())

    def test_student_cannot_toggle_another_students_task(self):
        self.client.force_login(self.leader)
        response = self.client.post(reverse("toggle_task", args=[self.task.pk]))
        self.assertEqual(response.status_code, 403)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "todo")

    def test_assignee_can_toggle_own_task(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("toggle_task", args=[self.task.pk]))
        self.assertEqual(response.status_code, 302)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "done")

    def test_group_manager_creates_task_from_the_task_catalog_for_group(self):
        self.client.force_login(self.leader)

        response = self.client.post(reverse("create_task", args=[self.group.pk]), {
            "title": "assignment",
            "description": "",
            "due_date": "",
        })

        self.assertRedirects(response, reverse("group_detail", args=[self.group.pk]))
        task = Task.objects.get(group=self.group, assigned_to__isnull=True)
        self.assertIn(task.title, ["حل تكليف", "Complete an assignment"])

    def test_group_task_is_visible_and_actionable_by_members_only(self):
        task = Task.objects.create(
            group=self.group,
            title="Shared milestone",
            created_by=self.leader,
            is_current=True,
        )
        self.client.force_login(self.member)

        dashboard_response = self.client.get(reverse("dashboard"))
        group_response = self.client.get(reverse("group_detail", args=[self.group.pk]))
        toggle_response = self.client.post(reverse("toggle_task", args=[task.pk]))

        self.assertContains(dashboard_response, "Shared milestone")
        self.assertContains(group_response, "Shared milestone")
        self.assertTrue(
            "GROUP TASK" in group_response.content.decode()
            or "مهمة للمجموعة" in group_response.content.decode()
        )
        self.assertEqual(toggle_response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, "done")

        self.client.force_login(self.outsider)
        denied_response = self.client.post(reverse("toggle_task", args=[task.pk]))
        self.assertEqual(denied_response.status_code, 403)

    def test_join_decision_requires_post(self):
        from .models import JoinRequest
        request_obj = JoinRequest.objects.create(group=self.group, student=self.outsider)
        self.client.force_login(self.leader)
        response = self.client.get(reverse("decide_join", args=[request_obj.pk, "accept"]))
        self.assertEqual(response.status_code, 405)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "pending")


class UploadSecurityTests(TestCase):
    def test_rejects_executable_extension(self):
        upload = SimpleUploadedFile("malware.exe", b"MZ" + b"0" * 20)
        with self.assertRaises(ValidationError):
            validate_submission_file(upload)

    def test_rejects_pdf_with_wrong_signature(self):
        upload = SimpleUploadedFile("fake.pdf", b"not a pdf")
        with self.assertRaises(ValidationError):
            validate_submission_file(upload)

    def test_accepts_valid_pdf_signature(self):
        upload = SimpleUploadedFile("report.pdf", b"%PDF-1.7\nexample")
        validate_submission_file(upload)

    def test_rejects_large_upload(self):
        upload = SimpleUploadedFile("large.txt", b"a" * (10 * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            validate_submission_file(upload)


class AnalyticsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="analyst", password="StrongPass!234")
        self.group = StudyGroup.objects.create(name="Analytics", leader=self.student)
        self.task = Task.objects.create(
            group=self.group, assigned_to=self.student, title="One task",
            created_by=self.student, status="done"
        )

    def test_analytics_counts_and_completion_rate(self):
        metrics = build_group_analytics([self.task])
        self.assertEqual(metrics["total"], 1)
        self.assertEqual(metrics["completed"], 1)
        self.assertEqual(metrics["completion_rate"], 100)

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_ai_fallback_works_without_api_key(self):
        result = generate_group_insight([self.task], group_id=self.group.pk)
        self.assertEqual(result["provider"], "local")
        self.assertIn("100%", result["text"])

    def test_ai_plan_and_student_productivity_are_generated(self):
        productivity = build_student_productivity(self.student, Task.objects.filter(group=self.group))
        self.assertEqual(productivity["total"], 1)
        self.assertEqual(productivity["completion_rate"], 100)

        group_task = Task.objects.create(
            group=self.group, title="Group task", created_by=self.student
        )
        self.group.members.add(self.student)
        productivity = build_student_productivity(
            self.student, Task.objects.filter(group=self.group)
        )
        self.assertEqual(productivity["total"], 2)
        self.assertIn(group_task, productivity["priority_tasks"])

        plan = generate_group_plan([self.task], group_id=self.group.pk)
        self.assertIn("warning", plan)
        self.assertGreater(len(plan["recommendations"]), 0)

    def test_deadline_alerts_detect_overdue_and_due_soon(self):
        self.task.due_date = None
        self.task.save(update_fields=["due_date"])
        due_soon = Task.objects.create(
            group=self.group,
            assigned_to=self.student,
            title="Due soon",
            created_by=self.student,
            due_date=date.today() + timedelta(days=1),
        )
        overdue = Task.objects.create(
            group=self.group,
            assigned_to=self.student,
            title="Late task",
            created_by=self.student,
            due_date=date.today() - timedelta(days=2),
        )

        alerts = build_deadline_alerts(Task.objects.filter(group=self.group))
        titles = {alert["task"].title for alert in alerts}
        self.assertIn("Due soon", titles)
        self.assertIn("Late task", titles)


class RealtimeNoticeTests(TestCase):
    @override_settings(CHANNEL_LAYERS={
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    })
    def test_notice_is_broadcast_to_recipient_channel(self):
        recipient = User.objects.create_user(username="notice-user", password="StrongPass!234")
        layer = get_channel_layer()
        channel_name = async_to_sync(layer.new_channel)()
        group_name = f"user_{recipient.pk}"
        async_to_sync(layer.group_add)(group_name, channel_name)
        Notice.objects.create(recipient=recipient, message="Task assigned")
        event = async_to_sync(layer.receive)(channel_name)
        self.assertEqual(event["type"], "notification.message")
        self.assertEqual(event["payload"]["message"], "Task assigned")
        async_to_sync(layer.group_discard)(group_name, channel_name)


class GroupChatWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.leader = User.objects.create_user(username="chat-leader", password="pass")
        self.student = User.objects.create_user(username="chat-student", password="pass")
        self.teacher = User.objects.create_user(username="chat-teacher", password="pass", role="teacher")
        self.outsider = User.objects.create_user(username="chat-outsider", password="pass")
        self.group = StudyGroup.objects.create(name="Chat group", leader=self.leader)
        self.group.members.add(self.leader, self.student)
        self.group.teachers.add(self.teacher)
        self.application = URLRouter(websocket_urlpatterns)
        self.path = f"/ws/groups/{self.group.pk}/chat/"

    async def test_members_and_supervisors_chat_in_real_time_and_messages_persist(self):
        student_socket = WebsocketCommunicator(self.application, self.path)
        student_socket.scope["user"] = self.student
        teacher_socket = WebsocketCommunicator(self.application, self.path)
        teacher_socket.scope["user"] = self.teacher

        student_connected, _ = await student_socket.connect()
        teacher_connected, _ = await teacher_socket.connect()
        self.assertTrue(student_connected)
        self.assertTrue(teacher_connected)

        try:
            await student_socket.send_json_to({"content": "Hello supervisor"})
            student_message = await student_socket.receive_json_from()
            teacher_message = await teacher_socket.receive_json_from()
            self.assertEqual(student_message["content"], "Hello supervisor")
            self.assertEqual(teacher_message["sender"], self.student.username)

            count = await database_sync_to_async(
                ChatMessage.objects.filter(group_id=self.group.pk).count
            )()
            self.assertEqual(count, 1)
        finally:
            await student_socket.disconnect()
            await teacher_socket.disconnect()

    async def test_non_member_cannot_connect_to_group_chat(self):
        outsider_socket = WebsocketCommunicator(self.application, self.path)
        outsider_socket.scope["user"] = self.outsider

        connected, close_code = await outsider_socket.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    async def test_blank_or_oversized_messages_are_rejected(self):
        student_socket = WebsocketCommunicator(self.application, self.path)
        student_socket.scope["user"] = self.student
        connected, _ = await student_socket.connect()
        self.assertTrue(connected)

        try:
            await student_socket.send_json_to({"content": "   "})
            self.assertEqual(
                await student_socket.receive_json_from(),
                {"type": "error", "code": "invalid_message"},
            )
            await student_socket.send_json_to({"content": "x" * 2001})
            self.assertEqual(
                await student_socket.receive_json_from(),
                {"type": "error", "code": "invalid_message"},
            )

            count = await database_sync_to_async(
                ChatMessage.objects.filter(group_id=self.group.pk).count
            )()
            self.assertEqual(count, 0)
        finally:
            await student_socket.disconnect()

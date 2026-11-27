from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import StudyGroup


class EmailLoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student",
            email="student@example.com",
            password="test-password-123",
            role="student",
        )

    def test_login_accepts_email_case_insensitively(self):
        response = self.client.post(
            reverse("login"),
            {"username": "STUDENT@example.com", "password": "test-password-123"},
        )

        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_form_requests_email(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, 'type="email"', html=False)
        self.assertContains(response, "البريد الإلكتروني")

    def test_about_page_describes_project_in_both_languages(self):
        response = self.client.get(reverse("about"))

        self.assertContains(response, "فكرة SmartGrad")
        self.assertContains(response, "الذكاء الاصطناعي")

        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("about")},
        )
        response = self.client.get(reverse("about"))

        self.assertContains(response, "The idea behind SmartGrad")
        self.assertContains(response, "AI-assisted analytics")


class PublicProjectPagesTests(TestCase):
    def test_intro_get_started_opens_main_landing_page(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "بوابة SmartGrad")
        self.assertContains(response, "images/smartgrad-brand.png")
        self.assertContains(response, reverse("main_landing"))

        response = self.client.get(reverse("main_landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "images/smartgrad-brand.png")
        self.assertContains(response, reverse("projects"))

        response = self.client.get(reverse("welcome"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تصفح المشاريع")
        self.assertContains(response, reverse("login"))

    def test_project_catalog_is_public_and_links_to_similar_websites(self):
        response = self.client.get(reverse("projects"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trello")
        self.assertContains(response, "Asana")
        self.assertContains(response, "Notion")
        self.assertContains(response, "https://trello.com/")
        self.assertContains(response, "https://asana.com/")
        self.assertNotContains(response, "github.com")


class LanguageSwitchTests(TestCase):
    def test_language_switch_updates_registration_ui_and_direction(self):
        response = self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("register")},
        )

        self.assertRedirects(response, reverse("register"))
        response = self.client.get(reverse("register"))

        self.assertContains(response, '<html lang="en" dir="ltr">', html=False)
        self.assertContains(response, "Create your account")
        self.assertContains(response, "University ID")
        self.assertContains(response, "SmartGrad")
        self.assertContains(response, "images/smartgrad-logo.png")

    def test_arabic_language_updates_group_page_and_ai_summary(self):
        user_model = get_user_model()
        student = user_model.objects.create_user(
            username="student",
            password="test-password",
            first_name="Student",
            role="student",
        )
        group = StudyGroup.objects.create(name="Study group", leader=student)
        group.members.add(student)
        self.client.force_login(student)

        self.client.post(
            reverse("set_language"),
            {"language": "en", "next": reverse("group_detail", args=[group.pk])},
        )
        english_response = self.client.get(
            reverse("group_detail", args=[group.pk])
        )
        self.assertContains(english_response, "Current tasks")
        self.assertContains(english_response, "Need AI help?")
        self.assertContains(english_response, '<details class="ai-help">', html=False)
        self.assertContains(english_response, "Group summary:")

        self.client.post(
            reverse("set_language"),
            {"language": "ar", "next": reverse("group_detail", args=[group.pk])},
        )
        arabic_response = self.client.get(
            reverse("group_detail", args=[group.pk])
        )
        self.assertContains(arabic_response, '<html lang="ar" dir="rtl">', html=False)
        self.assertContains(arabic_response, "المهام الحالية")
        self.assertContains(arabic_response, "هل تحتاج مساعدة من الذكاء الاصطناعي؟")
        self.assertContains(arabic_response, "ملخص المجموعة:")
        self.assertContains(arabic_response, "SmartGrad")

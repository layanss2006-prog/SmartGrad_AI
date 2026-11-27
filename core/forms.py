from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import get_language
from django.utils.crypto import get_random_string
from .models import User, StudyGroup, Task, Submission, AISettings
from .validators import validate_submission_file


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="البريد الإلكتروني")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if get_language() == "ar":
            self.fields["username"].label = "البريد الإلكتروني"
            self.error_messages["invalid_login"] = "البريد الإلكتروني أو كلمة المرور غير صحيحة."
        else:
            self.fields["username"].label = "Email address"
            self.error_messages["invalid_login"] = "Enter a correct email address and password."
        self.fields["username"].widget.attrs.update({
            "autocomplete": "email",
            "placeholder": "name@example.com",
        })


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="البريد الإلكتروني")
    first_name = forms.CharField(label="الاسم")
    university_id = forms.CharField(label="الرقم الجامعي", required=False)
    major = forms.CharField(label="التخصص", required=False)
    role = forms.ChoiceField(label="نوع الحساب", choices=User.ROLE_CHOICES)
    class Meta:
        model = User
        fields = ("email", "first_name", "university_id", "major", "role", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Both account types are visible and teachers can log in immediately after signup.
        self.fields["role"].choices = [
            ("student", "طالب" if get_language() == "ar" else "Student"),
            ("teacher", "أستاذ / مشرف" if get_language() == "ar" else "Teacher / Supervisor"),
        ]
        if get_language() == "ar":
            labels = {
                "email": "البريد الإلكتروني",
                "first_name": "الاسم",
                "university_id": "الرقم الجامعي",
                "major": "التخصص",
                "role": "نوع الحساب",
                "password1": "كلمة المرور",
                "password2": "تأكيد كلمة المرور",
            }
            for name, label in labels.items():
                self.fields[name].label = label
        else:
            labels = {
                "email": "Email address",
                "first_name": "Name",
                "university_id": "University ID",
                "major": "Major",
                "role": "Account type",
                "password1": "Password",
                "password2": "Confirm password",
            }
            for name, label in labels.items():
                self.fields[name].label = label

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "هذا البريد الإلكتروني مستخدم بالفعل."
                if get_language() == "ar"
                else "An account with this email address already exists."
            )
        return email


    def save(self, commit=True):
        user = super().save(commit=False)
        while not user.username or User.objects.filter(username=user.username).exists():
            user.username = f"smartgrad-{get_random_string(20)}"
        if commit:
            user.save()
            self.save_m2m()
        return user


class GroupForm(forms.ModelForm):
    class Meta:
        model = StudyGroup
        fields = ("name", "description")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if get_language() == "ar":
            self.fields["name"].label = "اسم المجموعة"
            self.fields["description"].label = "الوصف"

class TaskForm(forms.ModelForm):
    TASK_CHOICES = [
        ("assignment", "حل تكليف", "Complete an assignment"),
        ("quiz", "حل كويز", "Complete a quiz"),
        ("midterm", "حل الاختبار النصفي", "Take the midterm exam"),
        ("lecture", "حضور محاضرة", "Attend a lecture"),
        ("final", "حل الاختبار النهائي", "Take the final exam"),
        ("graduation_project", "حل مشروع التخرج", "Complete graduation project work"),
        ("project_idea", "اختيار فكرة المشروع", "Choose a project idea"),
        ("project_research", "البحث عن مصادر ومراجع للمشروع", "Research project sources and references"),
        ("project_requirements", "جمع وتحليل متطلبات المشروع", "Gather and analyze project requirements"),
        ("project_design", "تصميم المشروع", "Design the project"),
        ("project_development", "تنفيذ وتطوير المشروع", "Build and develop the project"),
        ("project_testing", "اختبار المشروع وتحسينه", "Test and improve the project"),
        ("project_report", "كتابة تقرير المشروع", "Write the project report"),
        ("project_presentation", "إعداد عرض المشروع", "Prepare the project presentation"),
        ("team_meeting", "اجتماع فريق المشروع", "Hold a project team meeting"),
        ("project_submission", "تسليم المشروع النهائي", "Submit the final project"),
        ("other_project_task", "مهمة أخرى متعلقة بالمشروع", "Other project-related task"),
    ]

    title = forms.ChoiceField()

    class Meta:
        model = Task
        fields = ("title", "description", "start_date", "due_date", "is_current")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        is_arabic = get_language() == "ar"
        self.fields["title"].choices = [
            ("", "اختر مهمة" if is_arabic else "Select a task"),
            *[
                (key, arabic if is_arabic else english)
                for key, arabic, english in self.TASK_CHOICES
            ],
        ]
        self.fields["title"].label = "المهمة" if is_arabic else "Task"
        self.fields["title"].widget.attrs["class"] = "task-choice"
        self.fields["description"].required = False

        if is_arabic:
            labels = {
                "description": "تفاصيل المهمة (اختياري)",
                "start_date": "تاريخ البدء",
                "due_date": "الموعد النهائي",
                "is_current": "المهمة الحالية",
            }
        else:
            labels = {
                "description": "Task details (optional)",
                "start_date": "Start date",
                "due_date": "Due date",
                "is_current": "Current task",
            }
        for name, label in labels.items():
            self.fields[name].label = label

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")
        if start_date and due_date and due_date < start_date:
            is_arabic = get_language() == "ar"
            raise forms.ValidationError(
                "يجب أن يكون الموعد النهائي في تاريخ البدء أو بعده."
                if is_arabic
                else "The deadline must be on or after the start date."
            )
        return cleaned_data

    def clean_title(self):
        selected = self.cleaned_data["title"]
        is_arabic = get_language() == "ar"
        return next(
            arabic if is_arabic else english
            for key, arabic, english in self.TASK_CHOICES
            if key == selected
        )

class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("file", "note")

    def clean_file(self):
        uploaded = self.cleaned_data.get("file")
        if uploaded:
            validate_submission_file(uploaded)
        return uploaded

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if get_language() == "ar":
            self.fields["file"].label = "الملف"
            self.fields["note"].label = "ملاحظة"


class AISettingsForm(forms.ModelForm):
    model_name = forms.ChoiceField(
        choices=[
            ("gpt-4o-mini", "gpt-4o-mini"),
            ("gpt-4o", "gpt-4o"),
            ("gpt-4.1-mini", "gpt-4.1-mini"),
        ],
        required=True,
    )

    class Meta:
        model = AISettings
        fields = ("api_key", "model_name")
        widgets = {
            "api_key": forms.PasswordInput(render_value=True),
        }

    def clean_api_key(self):
        value = (self.cleaned_data.get("api_key") or "").strip()
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if get_language() == "ar":
            self.fields["api_key"].label = "مفتاح OpenAI"
            self.fields["api_key"].help_text = "يتم استخدامه فقط لتحليلات ومخططات الفريق."
            self.fields["model_name"].label = "نموذج الذكاء"
            self.fields["model_name"].help_text = "اختر النموذج المناسب لتحليل المشروع وتوصياته."
        else:
            self.fields["api_key"].label = "OpenAI API key"
            self.fields["api_key"].help_text = "Used only for team analytics and project recommendations."
            self.fields["model_name"].label = "AI model"
            self.fields["model_name"].help_text = "Choose the model used for analysis and recommendations."

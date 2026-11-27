from datetime import timedelta
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import OperationalError
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.utils.translation import get_language
from .forms import RegisterForm, GroupForm, TaskForm, SubmissionForm, AISettingsForm
from .models import StudyGroup, JoinRequest, Task, Submission, Notice, User, AISettings
from .ai import build_student_productivity, build_student_report, build_group_report, build_teacher_monitoring, build_deadline_alerts, generate_group_insight, generate_group_plan, suggest_auto_tasks, summarize_group_for_teacher
from .permissions import can_access_group, can_manage_group

def localized_message(request, arabic, english):
    return english if get_language() == "en" else arabic


def ensure_database_ready():
    try:
        User._meta.default_manager.exists()
    except OperationalError:
        call_command("migrate", verbosity=0, interactive=False)


def notify(user, message):
    Notice.objects.create(recipient=user, message=message)


def create_deadline_notifications_for_user(user, tasks):
    for task in tasks:
        if task.status == "done" or not task.due_date:
            continue
        days_left = (task.due_date - timezone.now().date()).days
        if days_left > 3:
            continue
        if task.assigned_to_id != user.pk and not (
            task.assigned_to_id is None
            and task.group.members.filter(pk=user.pk).exists()
        ):
            continue
        message = (
            f"Deadline alert: '{task.title}' is due {('today' if days_left == 0 else 'tomorrow' if days_left == 1 else f'in {days_left} days')}."
            if get_language() == "en"
            else f"تنبيه موعد: المهمة '{task.title}' تستحق {('اليوم' if days_left == 0 else 'غداً' if days_left == 1 else f'خلال {days_left} أيام')}."
        )
        recent = Notice.objects.filter(recipient=user, message=message, created_at__gte=timezone.now() - timedelta(days=7))
        if not recent.exists():
            Notice.objects.create(recipient=user, message=message)


def create_deadline_notifications_for_group(group, tasks):
    recipients = {
        user.pk: user
        for user in [group.leader, *group.teachers.all(), *group.members.all()]
    }
    for recipient in recipients.values():
        for task in tasks:
            if task.status == "done" or not task.due_date:
                continue
            days_left = (task.due_date - timezone.now().date()).days
            if days_left > 3:
                continue
            due_text = (
                "today" if days_left == 0 else "tomorrow" if days_left == 1
                else f"in {days_left} days"
            ) if get_language() == "en" else (
                "اليوم" if days_left == 0 else "غداً" if days_left == 1
                else f"خلال {days_left} أيام"
            )
            if task.assigned_to_id:
                assignee = task.assigned_to.get_full_name() or task.assigned_to.username
                message = (
                    f"Deadline alert: '{task.title}' for {assignee} is due {due_text}."
                    if get_language() == "en"
                    else f"تنبيه موعد: المهمة '{task.title}' للطالب {assignee} تستحق {due_text}."
                )
            else:
                message = (
                    f"Group deadline alert: '{task.title}' is due {due_text}."
                    if get_language() == "en"
                    else f"تنبيه موعد للمجموعة: المهمة '{task.title}' تستحق {due_text}."
                )
            recent = Notice.objects.filter(
                recipient=recipient,
                message=message,
                created_at__gte=timezone.now() - timedelta(days=7),
            )
            if not recent.exists():
                Notice.objects.create(recipient=recipient, message=message)


def register(request):
    ensure_database_ready()
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend="core.backends.EmailBackend")
            return redirect("dashboard")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


def about(request):
    return render(request, "core/about.html")


def dashboard(request):
    if not request.user.is_authenticated:
        return render(request, "core/intro.html")

    if request.user.role == "teacher":
        groups = StudyGroup.objects.filter(Q(leader=request.user) | Q(teachers=request.user)).distinct()
        tasks = Task.objects.filter(group__in=groups).select_related("assigned_to", "group")
        teacher_metrics = build_teacher_monitoring(groups, tasks)
        for group in groups:
            create_deadline_notifications_for_group(group, group.tasks.select_related("assigned_to"))
    else:
        groups = request.user.study_groups.all()
        tasks = Task.objects.filter(group__in=groups).filter(
            Q(assigned_to=request.user) | Q(assigned_to__isnull=True)
        ).select_related("group")
        teacher_metrics = None
        create_deadline_notifications_for_user(request.user, tasks)
    notices = request.user.notices.order_by("-created_at")[:12]
    context = {
        "groups": groups, "tasks": tasks,
        "completed_tasks": tasks.filter(status="done").count(),
        "in_progress_tasks": tasks.filter(status="doing").count(),
        "pending_tasks": tasks.exclude(status="done").count(),
        "notices": notices,
    }
    if request.user.role == "teacher":
        context["student_count"] = User.objects.filter(study_groups__in=groups, role="student").distinct().count()
        context["pending_join_requests"] = JoinRequest.objects.filter(group__in=groups, status="pending").count()
        context["teacher_monitoring"] = teacher_metrics
        context["deadline_alerts"] = build_deadline_alerts(tasks)
        template = "core/dashboard_teacher.html"
    else:
        context["student_metrics"] = build_student_productivity(request.user, tasks)
        context["deadline_alerts"] = build_deadline_alerts(tasks)
        template = "core/dashboard_student.html"
    return render(request, template, context)


def projects(request):
    return render(request, "core/projects.html")


def welcome(request):
    return render(request, "core/welcome.html")


def main_landing(request):
    return render(request, "core/landing.html")


@login_required
def ai_settings(request):
    if request.user.role != "teacher":
        raise PermissionDenied
    settings_obj, _ = AISettings.objects.get_or_create(pk=1)
    form = AISettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, localized_message(request, "تم حفظ إعدادات الذكاء الاصطناعي.", "AI settings were saved."))
        return redirect("dashboard")
    return render(request, "core/ai_settings.html", {"form": form})


@login_required
def teacher_summary(request):
    if request.user.role != "teacher":
        raise PermissionDenied
    groups = StudyGroup.objects.filter(Q(leader=request.user) | Q(teachers=request.user)).distinct()
    summaries = []
    for group in groups:
        tasks = list(group.tasks.select_related("assigned_to"))
        summaries.append(summarize_group_for_teacher(group, tasks))
    return render(request, "core/teacher_summary.html", {"summaries": summaries})


@login_required
def student_report(request):
    groups = request.user.study_groups.all()
    tasks = Task.objects.filter(group__in=groups).filter(
        Q(assigned_to=request.user) | Q(assigned_to__isnull=True)
    ).select_related("group")
    report = build_student_report(request.user, tasks)
    return render(request, "core/student_report.html", {"report": report, "tasks": tasks})


@login_required
def group_report(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_access_group(request.user, group):
        raise PermissionDenied
    tasks = group.tasks.select_related("assigned_to")
    report = build_group_report(group, tasks)
    return render(request, "core/group_report.html", {"group": group, "tasks": tasks, "report": report, "can_manage": can_manage_group(request.user, group)})


@login_required
def create_group(request):
    form = GroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.leader = request.user
        group.save()
        if request.user.role == "student":
            group.members.add(request.user)
        else:
            group.teachers.add(request.user)
        messages.success(request, localized_message(request, "تم إنشاء المجموعة.", "Group created."))
        return redirect("group_detail", pk=group.pk)
    return render(request, "core/form.html", {"form": form, "heading": localized_message(request, "إنشاء مجموعة", "Create group")})

@login_required
def group_detail(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_access_group(request.user, group):
        raise PermissionDenied
    tasks = group.tasks.select_related("assigned_to")
    own_tasks = tasks.filter(
        Q(assigned_to=request.user) | Q(assigned_to__isnull=True),
        is_current=True,
    )
    pending_requests = group.join_requests.filter(status="pending") if can_manage_group(request.user, group) else []
    chat_messages = list(
        group.chat_messages.select_related("sender").order_by("-created_at", "-pk")[:100]
    )
    chat_messages.reverse()
    ai_result = generate_group_insight(list(tasks), group_id=group.pk)
    plan = generate_group_plan(list(tasks), group_id=group.pk, group=group)
    deadline_alerts = build_deadline_alerts(tasks)
    return render(request, "core/group_detail.html", {
        "group": group, "tasks": tasks, "own_tasks": own_tasks,
        "pending_requests": pending_requests, "insight": ai_result["text"],
        "analytics": ai_result["metrics"], "ai_provider": ai_result["provider"],
        "plan": plan, "deadline_alerts": deadline_alerts,
        "chat_messages": chat_messages,
        "can_manage": can_manage_group(request.user, group),
    })

@login_required
@require_POST
def create_ai_task_plan(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied

    existing_tasks = list(group.tasks.select_related("assigned_to"))
    plan = suggest_auto_tasks(group, existing_tasks)
    created = []
    for task_data in plan.get("tasks", []):
        if group.tasks.filter(title__iexact=task_data["title"]).exists():
            continue
        task = Task.objects.create(
            group=group,
            assigned_to=task_data["assigned_to"],
            title=task_data["title"],
            description=task_data["description"],
            start_date=task_data.get("start_date"),
            due_date=task_data["due_date"],
            status=task_data["status"],
            is_current=task_data["is_current"],
            created_by=request.user,
        )
        created.append(task)
        notify(task.assigned_to, f"تم إنشاء خطة ذكية جديدة لك: {task.title}")

    if not created:
        messages.info(request, localized_message(request, "لا توجد مهام جديدة لإنشاء خطة ذكية إضافية.", "No new AI-generated tasks were created."))
    else:
        messages.success(request, localized_message(request, f"تم إنشاء {len(created)} مهمة تلقائياً من خطة الذكاء الاصطناعي.", f"{len(created)} AI-generated tasks were created automatically."))
    return redirect("group_detail", pk=group.pk)


@login_required
@require_http_methods(["GET", "POST"])
def join_by_code(request, code):
    group = get_object_or_404(StudyGroup, invite_code=code)
    if request.user.role != "student":
        raise PermissionDenied
    if request.method == "GET":
        return render(request, "core/join_confirm.html", {"group": group})
    if group.members.filter(pk=request.user.pk).exists():
        messages.info(request, localized_message(request, "أنت عضو بالفعل.", "You are already a member."))
    else:
        req, created = JoinRequest.objects.get_or_create(group=group, student=request.user)
        if not created and req.status != "pending":
            req.status = "pending"
            req.save(update_fields=["status"])
        notify(group.leader, f"طلب انضمام جديد من {request.user.get_full_name() or request.user.username} إلى {group.name}.")
        messages.success(request, localized_message(request, "أُرسل طلب الانضمام إلى قائدة المجموعة للموافقة.", "Your join request has been sent."))
    return redirect("dashboard")

@login_required
@require_POST
def decide_join(request, request_id, decision):
    join = get_object_or_404(JoinRequest.objects.select_related("group", "student"), pk=request_id)
    group = join.group
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    if join.status != "pending":
        messages.info(request, localized_message(request, "تمت معالجة هذا الطلب مسبقاً.", "This request has already been processed."))
    elif decision == "accept":
        join.status = "accepted"
        join.save(update_fields=["status"])
        group.members.add(join.student)
        notify(join.student, f"تم قبول طلبك للانضمام إلى {group.name}.")
        messages.success(request, localized_message(request, "تم قبول الطلب.", "Request accepted."))
    elif decision == "reject":
        join.status = "rejected"
        join.save(update_fields=["status"])
        notify(join.student, f"تم رفض طلب الانضمام إلى {group.name}.")
        messages.info(request, localized_message(request, "تم رفض الطلب.", "Request declined."))
    else:
        raise Http404
    return redirect("group_detail", pk=group.pk)

@login_required
@require_POST
def add_member(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    uid = request.POST.get("university_id", "").strip()
    student = User.objects.filter(university_id=uid, role="student", is_active=True).first()
    if student:
        group.members.add(student)
        notify(student, f"أُضيفت إلى مجموعة {group.name}.")
        messages.success(request, localized_message(request, "تمت إضافة الطالب.", "Student added."))
    else:
        messages.error(request, localized_message(request, "لم يتم العثور على طالب بهذا الرقم الجامعي.", "No active student was found with that university ID."))
    return redirect("group_detail", pk=pk)

@login_required
@require_POST
def add_teacher(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    teacher = User.objects.filter(username=request.POST.get("username", "").strip(), role="teacher", is_active=True).first()
    if teacher:
        group.teachers.add(teacher)
        notify(teacher, f"تمت إضافتك مشرفاً على مجموعة {group.name}.")
        messages.success(request, localized_message(request, "تمت إضافة المشرف.", "Teacher added."))
    else:
        messages.error(request, localized_message(request, "اسم المستخدم غير صحيح أو ليس حساب مشرف.", "No active teacher was found with that username."))
    return redirect("group_detail", pk=pk)

@login_required
def create_task(request, pk):
    group = get_object_or_404(StudyGroup, pk=pk)
    if not can_manage_group(request.user, group):
        raise PermissionDenied
    form = TaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.group, task.created_by = group, request.user
        task.save()
        recipients = {
            member.pk: member
            for member in [group.leader, *group.teachers.all(), *group.members.all()]
        }
        notification = localized_message(
            request,
            f"أُضيفت مهمة جديدة للمجموعة «{group.name}»: {task.title}",
            f"A new task was added to {group.name}: {task.title}",
        )
        for recipient in recipients.values():
            if recipient.pk != request.user.pk:
                notify(recipient, notification)
        messages.success(request, localized_message(request, "تمت إضافة المهمة إلى المجموعة وإشعار أعضائها.", "Task added to the group and its members were notified."))
        return redirect("group_detail", pk=pk)
    return render(request, "core/form.html", {"form": form, "heading": localized_message(request, "إضافة مهمة", "Add task")})

@login_required
@require_POST
def toggle_task(request, task_id):
    task = get_object_or_404(Task.objects.select_related("group", "assigned_to"), pk=task_id)
    if not can_access_group(request.user, task.group):
        raise PermissionDenied
    if (
        request.user.role == "student"
        and task.assigned_to_id is not None
        and request.user.pk != task.assigned_to_id
    ):
        raise PermissionDenied
    if request.user.role == "teacher" and not can_manage_group(request.user, task.group):
        raise PermissionDenied
    task.status = "done" if task.status != "done" else "todo"
    task.save(update_fields=["status"])
    notify(task.created_by, f"تم تحديث حالة المهمة «{task.title}» بواسطة {request.user.get_full_name() or request.user.username}.")
    messages.success(request, localized_message(request, "تم تحديث حالة المهمة.", "Task status updated."))
    return redirect("group_detail", pk=task.group_id)

@login_required
def upload_submission(request, task_id):
    task = get_object_or_404(Task.objects.select_related("group", "assigned_to"), pk=task_id)
    if (
        not can_access_group(request.user, task.group)
        or (
            task.assigned_to_id is not None
            and request.user.pk != task.assigned_to_id
        )
    ):
        raise PermissionDenied
    form = SubmissionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        submission = form.save(commit=False)
        submission.task, submission.uploaded_by = task, request.user
        submission.save()
        notify(task.created_by, f"تم رفع تسليم جديد للمهمة: {task.title}.")
        messages.success(request, localized_message(request, "تم رفع الملف بنجاح.", "File uploaded successfully."))
        return redirect("group_detail", pk=task.group_id)
    return render(request, "core/form.html", {"form": form, "heading": localized_message(request, "رفع ملف المهمة", "Upload task file")})

@login_required
def download_submission(request, submission_id):
    submission = get_object_or_404(Submission.objects.select_related("task__group"), pk=submission_id)
    group = submission.task.group
    if not can_access_group(request.user, group):
        raise PermissionDenied
    try:
        handle = submission.file.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    return FileResponse(handle, as_attachment=True, filename=submission.file.name.rsplit("/", 1)[-1])

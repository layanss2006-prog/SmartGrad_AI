from django.urls import path
from . import views

urlpatterns = [
    path("about/", views.about, name="about"),
    path("projects/", views.projects, name="projects"),
    path("welcome/", views.welcome, name="welcome"),
    path("home/", views.main_landing, name="main_landing"),
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("ai-settings/", views.ai_settings, name="ai_settings"),
    path("teacher-summary/", views.teacher_summary, name="teacher_summary"),
    path("reports/student/", views.student_report, name="student_report"),
    path("groups/create/", views.create_group, name="create_group"),
    path("groups/<int:pk>/ai-plan/", views.create_ai_task_plan, name="create_ai_plan"),
    path("groups/<int:pk>/report/", views.group_report, name="group_report"),
    path("groups/<int:pk>/", views.group_detail, name="group_detail"),
    path("groups/<int:pk>/members/add/", views.add_member, name="add_member"),
    path("groups/<int:pk>/teachers/add/", views.add_teacher, name="add_teacher"),
    path("groups/<int:pk>/tasks/create/", views.create_task, name="create_task"),
    path("groups/join/<uuid:code>/", views.join_by_code, name="join_by_code"),
    path("join-request/<int:request_id>/<str:decision>/", views.decide_join, name="decide_join"),
    path("tasks/<int:task_id>/toggle/", views.toggle_task, name="toggle_task"),
    path("tasks/<int:task_id>/upload/", views.upload_submission, name="upload_submission"),
    path("submissions/<int:submission_id>/download/", views.download_submission, name="download_submission"),
]

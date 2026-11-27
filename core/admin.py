from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, StudyGroup, JoinRequest, Task, Submission, Notice, AISettings

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("بيانات أكاديمية", {"fields": ("role", "university_id", "major", "avatar")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("بيانات أكاديمية", {"fields": ("role", "university_id", "major")}),)

admin.site.register([StudyGroup, JoinRequest, Task, Submission, Notice, AISettings])

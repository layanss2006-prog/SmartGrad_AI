import os
from datetime import date, timedelta
from django.core.cache import cache
from django.db.models import Q
from django.utils.translation import get_language


def get_openai_config():
    try:
        from .models import AISettings
        settings_obj = AISettings.objects.filter(pk=1).first()
        if settings_obj and settings_obj.api_key.strip():
            return settings_obj.api_key.strip(), settings_obj.model_name.strip() or "gpt-4o-mini"
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "").strip(), os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def build_group_analytics(tasks):
    today = date.today()
    total = len(tasks)
    done = sum(t.status == "done" for t in tasks)
    doing = sum(t.status == "doing" for t in tasks)
    todo = total - done - doing
    overdue = sum(bool(t.due_date and t.due_date < today and t.status != "done") for t in tasks)
    due_soon = sum(bool(t.due_date and today <= t.due_date and (t.due_date - today).days <= 3 and t.status != "done") for t in tasks)
    completion = round((done / total) * 100) if total else 0
    workload = {}
    for task in tasks:
        if task.assigned_to_id is not None:
            workload[task.assigned_to_id] = workload.get(task.assigned_to_id, 0) + (task.status != "done")
    group_assignments = sum(
        task.assigned_to_id is None and task.status != "done"
        for task in tasks
    )
    return {
        "total": total, "completed": done, "in_progress": doing, "not_started": todo,
        "overdue": overdue, "due_soon": due_soon, "completion_rate": completion,
        "active_assignments": sum(workload.values()) + group_assignments,
        "member_count": len(workload),
    }


def build_student_productivity(user, tasks):
    assigned = list(
        tasks.filter(
            Q(assigned_to=user)
            | Q(assigned_to__isnull=True, group__members=user)
        ).distinct().select_related("group")
    )
    today = date.today()
    completed = sum(task.status == "done" for task in assigned)
    overdue = sum(bool(task.due_date and task.due_date < today and task.status != "done") for task in assigned)
    due_soon = sum(bool(task.due_date and today <= task.due_date and (task.due_date - today).days <= 3 and task.status != "done") for task in assigned)
    completion = round((completed / len(assigned)) * 100) if assigned else 0
    next_deadline = min((task.due_date for task in assigned if task.due_date and task.status != "done"), default=None)
    return {
        "total": len(assigned),
        "completed": completed,
        "overdue": overdue,
        "due_soon": due_soon,
        "completion_rate": completion,
        "next_deadline": next_deadline,
        "priority_tasks": [task for task in sorted(assigned, key=lambda t: (t.due_date or date.max, t.pk)) if task.status != "done"][:3],
    }


def build_student_report(user, tasks):
    assigned = list(
        tasks.filter(
            Q(assigned_to=user)
            | Q(assigned_to__isnull=True, group__members=user)
        ).distinct().select_related("group")
    ) if hasattr(tasks, "filter") else [
        task for task in tasks
        if task.assigned_to_id == user.pk
        or (
            task.assigned_to_id is None
            and task.group.members.filter(pk=user.pk).exists()
        )
    ]
    if hasattr(tasks, "filter"):
        metrics = build_student_productivity(user, tasks)
    else:
        metrics = {
            "total": len(assigned),
            "completed": sum(task.status == "done" for task in assigned),
            "overdue": sum(bool(task.due_date and task.due_date < date.today() and task.status != "done") for task in assigned),
            "due_soon": sum(bool(task.due_date and date.today() <= task.due_date and (task.due_date - date.today()).days <= 3 and task.status != "done") for task in assigned),
            "completion_rate": round((sum(task.status == "done" for task in assigned) / len(assigned)) * 100) if assigned else 0,
            "next_deadline": min((task.due_date for task in assigned if task.due_date and task.status != "done"), default=None),
            "priority_tasks": [task for task in sorted(assigned, key=lambda t: (t.due_date or date.max, t.pk)) if task.status != "done"][:3],
        }

    recommendations = []
    if metrics["overdue"]:
        recommendations.append({"title": "Resolve overdue tasks", "description": "Start with the assignments that missed their due date to protect your momentum and avoid accumulation.", "priority": "High"})
    elif metrics["due_soon"]:
        recommendations.append({"title": "Prepare for upcoming deadlines", "description": "Review tasks due within the next three days and confirm the remaining work before the due date.", "priority": "Medium"})
    else:
        recommendations.append({"title": "Keep the momentum", "description": "Maintain the current pace by finishing the next milestone and preparing your final output early.", "priority": "Low"})

    recommendations.append({
        "title": "Check delivery quality",
        "description": "Before submission, verify file quality, formatting, and completeness to reduce avoidable revision cycles.",
        "priority": "Medium",
    })

    return {
        "user": user,
        "metrics": metrics,
        "recommendations": recommendations,
        "summary": "Student is on track" if metrics["completion_rate"] >= 70 else "Student needs closer follow-up" if metrics["overdue"] else "Student needs a sharper focus",
        "tasks": assigned,
    }


def build_group_report(group, tasks):
    metrics = build_group_analytics(list(tasks))
    student_rows = []
    for student in group.members.filter(role="student", is_active=True).distinct():
        student_tasks = [
            task for task in tasks
            if task.assigned_to_id == student.pk or task.assigned_to_id is None
        ]
        student_metrics = build_group_analytics(student_tasks)
        student_rows.append({
            "student": student,
            "metrics": student_metrics,
            "tasks": student_tasks,
        })
    plan = generate_group_plan(list(tasks), group_id=group.pk, group=group)
    return {
        "group": group,
        "metrics": metrics,
        "students": sorted(student_rows, key=lambda item: item["student"].username.lower()),
        "plan": plan,
        "summary": "Group is progressing well" if metrics["completion_rate"] >= 70 else "Group needs intervention" if metrics["overdue"] else "Group needs stronger monitoring",
    }


def build_teacher_monitoring(groups, tasks):
    open_tasks = list(tasks)
    metrics = build_group_analytics(open_tasks)
    at_risk_groups = []
    for group in groups:
        group_tasks = [task for task in open_tasks if task.group_id == group.pk]
        group_metrics = build_group_analytics(group_tasks)
        if group_metrics["overdue"] or group_metrics["due_soon"]:
            at_risk_groups.append({
                "name": group.name,
                "overdue": group_metrics["overdue"],
                "due_soon": group_metrics["due_soon"],
                "completion_rate": group_metrics["completion_rate"],
            })
    return {
        "total_tasks": metrics["total"],
        "overdue": metrics["overdue"],
        "due_soon": metrics["due_soon"],
        "completion_rate": metrics["completion_rate"],
        "at_risk_groups": at_risk_groups[:5],
    }


def build_deadline_alerts(tasks):
    today = date.today()
    alerts = []
    for task in tasks:
        if task.status == "done" or not task.due_date:
            continue
        days_left = (task.due_date - today).days
        if days_left < 0:
            severity = "critical"
            label = "Overdue"
            detail = f"{abs(days_left)} day(s) late"
        elif days_left == 0:
            severity = "warning"
            label = "Due today"
            detail = "Due today"
        elif days_left == 1:
            severity = "warning"
            label = "Due tomorrow"
            detail = "Due tomorrow"
        elif days_left <= 3:
            severity = "info"
            label = "Due soon"
            detail = f"Due in {days_left} day(s)"
        else:
            continue
        alerts.append({
            "task": task,
            "severity": severity,
            "label": label,
            "days_left": days_left,
            "detail": detail,
        })
    return sorted(alerts, key=lambda item: (item["days_left"], item["task"].pk))


def summarize_group_for_teacher(group, tasks):
    metrics = build_group_analytics(tasks)
    students = []
    for student in group.members.filter(role="student", is_active=True).distinct():
        student_tasks = [
            task for task in tasks
            if task.assigned_to_id == student.pk or task.assigned_to_id is None
        ]
        student_metrics = build_group_analytics(student_tasks)
        students.append({
            "student": student,
            "tasks": student_tasks,
            "metrics": student_metrics,
        })
    return {
        "group": group,
        "metrics": metrics,
        "students": sorted(students, key=lambda item: item["student"].username.lower()),
    }


def suggest_auto_tasks(group, tasks):
    today = date.today()
    members = list(group.members.filter(role="student", is_active=True).distinct()) if group else []
    if not members:
        return {"warning": "No members available", "recommendations": [], "tasks": []}

    base_steps = [
        ("Requirements review", "Clarify the project scope, criteria, and expected outputs."),
        ("Research and source collection", "Gather references, data, and evidence needed for the deliverable."),
        ("Draft implementation", "Draft the first working version and validate the main flow."),
        ("Review and polish", "Check quality, fix issues, and prepare final submission."),
    ]
    task_list = []
    for index, (title, description) in enumerate(base_steps):
        assignee = members[index % len(members)]
        due_date = today + timedelta(days=2 + index * 3)
        # Prevent duplicate generation for groups that already have the same task title.
        if any(task.title.lower() == title.lower() for task in tasks):
            continue
        task_list.append({
            "title": f"{group.name}: {title}" if group else title,
            "description": description,
            "assigned_to": assignee,
            "start_date": today,
            "due_date": due_date,
            "status": "todo",
            "is_current": index == 0,
        })

    if not task_list:
        return {"warning": "No new tasks generated", "recommendations": [], "tasks": []}

    metrics = build_group_analytics(list(tasks) + [type("TaskStub", (), {"status": "todo", "due_date": item["due_date"], "assigned_to_id": item["assigned_to"].pk})() for item in task_list])
    recommendations = []
    if metrics["overdue"]:
        recommendations.append({
            "phase": "Phase 1",
            "title": "Resolve overdue work",
            "description": "Stabilize the delayed deliverables before starting new incremental work.",
            "priority": "High",
        })
    else:
        recommendations.append({
            "phase": "Phase 1",
            "title": "Start with the next milestone",
            "description": "Begin with the first automated milestone and divide remaining work by student capacity.",
            "priority": "Medium",
        })

    recommendations.append({
        "phase": "Phase 2",
        "title": "Balance workload",
        "description": "Distribute tasks evenly so each member has a clear role and deadline.",
        "priority": "Medium",
    })
    recommendations.append({
        "phase": "Phase 3",
        "title": "Prepare final review",
        "description": "Reserve the last milestone for feedback, revisions, and final submission.",
        "priority": "High" if metrics["overdue"] else "Medium",
    })

    return {
        "warning": "Risk of delay" if metrics["overdue"] else "On track" if metrics["completion_rate"] >= 70 else "Needs a sharper focus",
        "recommendations": recommendations,
        "tasks": task_list,
    }


def generate_group_plan(tasks, group_id=None, group=None):
    metrics = build_group_analytics(tasks)
    recommendations = []
    if metrics["overdue"]:
        recommendations.append({
            "phase": "Phase 1",
            "title": "Resolve overdue work",
            "description": "Focus on delayed tasks before adding new ones to reduce risk and protect group momentum.",
            "priority": "High",
        })
    elif metrics["due_soon"]:
        recommendations.append({
            "phase": "Phase 1",
            "title": "Review due-soon tasks",
            "description": "Confirm owners and deadlines for tasks due within the next 3 days.",
            "priority": "Medium",
        })
    else:
        recommendations.append({
            "phase": "Phase 1",
            "title": "Keep momentum steady",
            "description": "Use the current rhythm to complete the next planned deliverables without overload.",
            "priority": "Low",
        })

    if metrics["in_progress"]:
        recommendations.append({
            "phase": "Phase 2",
            "title": "Balance active work",
            "description": "Move incomplete items into a clearer sequence so each student has a single priority target.",
            "priority": "Medium",
        })
    else:
        recommendations.append({
            "phase": "Phase 2",
            "title": "Start with the next deliverable",
            "description": "Break the project into small milestones and assign the first milestone to the most available member.",
            "priority": "Medium",
        })

    recommendations.append({
        "phase": "Phase 3",
        "title": "Review and protect deadlines",
        "description": "Check checkpoints, confirm which tasks are ready for submission, and assign final review before delivery.",
        "priority": "High" if metrics["overdue"] else "Medium",
    })

    if group is not None:
        auto_plan = suggest_auto_tasks(group, tasks)
        if auto_plan["tasks"]:
            recommendations.insert(0, {
                "phase": "AI Auto-Plan",
                "title": "Suggested automated milestones",
                "description": "The system can schedule a short milestone sequence for the group based on workload and due dates.",
                "priority": "High",
            })

    warning = "Risk of delay" if metrics["overdue"] else "On track" if metrics["completion_rate"] >= 70 else "Needs a sharper focus"
    return {
        "metrics": metrics,
        "warning": warning,
        "recommendations": recommendations,
        "provider": "local",
    }


def generate_group_insight(tasks, group_id=None):
    is_en = get_language() == "en"
    metrics = build_group_analytics(tasks)
    if is_en:
        fallback = (
            f"Completion: {metrics['completion_rate']}% ({metrics['completed']}/{metrics['total']}). "
            f"{metrics['overdue']} overdue, {metrics['due_soon']} due within 3 days. "
            "Prioritize overdue work, then confirm owners and deadlines for remaining tasks."
        )
    else:
        fallback = (
            f"نسبة الإنجاز: {metrics['completion_rate']}% "
            f"({metrics['completed']} من {metrics['total']}). "
            f"المهام المتأخرة: {metrics['overdue']}، والمهام المستحقة خلال 3 أيام: {metrics['due_soon']}. "
            "الأولوية لمعالجة المتأخرات ثم التأكد من وضوح المسؤول والموعد لكل مهمة."
        )
    api_key, model_name = get_openai_config()
    if not api_key or not total_has_tasks(metrics):
        return {"text": fallback, "metrics": metrics, "provider": "local"}
    cache_key = f"smartgrad_ai_{group_id}_{get_language()}_{metrics['total']}_{metrics['completed']}_{metrics['overdue']}"
    cached = cache.get(cache_key)
    if cached:
        return {"text": cached, "metrics": metrics, "provider": "openai"}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=12.0, max_retries=1)
        language = "English" if is_en else "Arabic"
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": (
                    f"You are SmartGrad, an academic project coach. Respond in {language}. "
                    "Use only the supplied aggregate metrics. Never invent student names, task details, "
                    "or causes. Return a concise status assessment, up to three prioritized actions, "
                    "and one risk warning if metrics support it."
                )},
                {"role": "user", "content": f"Group task analytics (aggregate only): {metrics}"},
            ],
            max_tokens=280,
            temperature=0.2,
        )
        result = (response.choices[0].message.content or fallback).strip()
        cache.set(cache_key, result, 300)
        return {"text": result, "metrics": metrics, "provider": "openai"}
    except Exception:
        return {"text": fallback, "metrics": metrics, "provider": "local-fallback"}


def total_has_tasks(metrics):
    return metrics["total"] > 0

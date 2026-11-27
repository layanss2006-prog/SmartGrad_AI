def can_access_group(user, group):
    return bool(
        user.is_authenticated and (
            group.leader_id == user.pk
            or group.members.filter(pk=user.pk).exists()
            or group.teachers.filter(pk=user.pk).exists()
        )
    )

def can_manage_group(user, group):
    return bool(
        user.is_authenticated and (
            group.leader_id == user.pk
            or group.teachers.filter(pk=user.pk).exists()
        )
    )

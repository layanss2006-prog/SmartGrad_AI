from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = kwargs.get("email", username)
        if email is None or password is None:
            return None

        user_model = get_user_model()
        users = list(user_model._default_manager.filter(email__iexact=email)[:2])
        if len(users) != 1:
            user_model().set_password(password)
            return None

        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

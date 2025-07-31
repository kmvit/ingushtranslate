from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(UserPassesTestMixin):
    """
    Универсальный миксин для проверки ролей пользователей.

    Использование:
        class MyView(RoleRequiredMixin, TemplateView):
            allowed_roles = ['admin', 'representative']
            # или
            allowed_roles = ['translator']
    """

    allowed_roles = []

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False

        if not self.allowed_roles:
            # Если роли не указаны, разрешаем доступ любому аутентифицированному пользователю
            return True

        return self.request.user.role in self.allowed_roles

    def handle_no_permission(self):
        """
        Переопределяем для более информативных сообщений об ошибке
        """
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()

        # Если пользователь аутентифицирован, но роль не подходит
        raise PermissionDenied(
            f"У вас нет доступа к этой странице. " f"Требуемые роли: {', '.join(self.allowed_roles)}"
        )


# Готовые миксины для часто используемых комбинаций ролей
class AdminOnlyMixin(RoleRequiredMixin):
    """Только для администраторов"""

    allowed_roles = ["admin"]


class AdminOrRepresentativeMixin(RoleRequiredMixin):
    """Для администраторов и представителей"""

    allowed_roles = ["admin", "representative"]


class TranslatorOnlyMixin(RoleRequiredMixin):
    """Только для переводчиков"""

    allowed_roles = ["translator"]


class CorrectorOnlyMixin(RoleRequiredMixin):
    """Только для корректоров"""

    allowed_roles = ["corrector"]


class TranslatorOrCorrectorMixin(RoleRequiredMixin):
    """Для переводчиков и корректоров"""

    allowed_roles = ["translator", "corrector"]


class DocumentAccessMixin(RoleRequiredMixin):
    """Для доступа к документам - админы, представители, переводчики и корректоры"""

    allowed_roles = ["admin", "representative", "translator", "corrector"]

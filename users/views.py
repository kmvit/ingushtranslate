from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import View
from .models import User


class LoginView(View):
    """Страница входа в систему"""

    template_name = "users/login.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Добро пожаловать, {user.get_full_name()}!")

            # Перенаправляем в соответствующий кабинет в зависимости от роли
            if user.role == "translator":
                return redirect("dashboards:translator_dashboard")
            elif user.role == "corrector":
                return redirect("dashboards:corrector_dashboard")
            elif user.role in ["admin", "representative"]:
                return redirect("dashboards:dashboard")
            else:
                return redirect("dashboards:dashboard")
        else:
            messages.error(request, "Неверное имя пользователя или пароль.")

        return render(request, self.template_name)


class LogoutView(LoginRequiredMixin, View):
    """Выход из системы"""

    def get(self, request):
        logout(request)
        messages.info(request, "Вы успешно вышли из системы.")
        return redirect("users:login")


class RegisterView(View):
    """Регистрация нового пользователя"""

    template_name = "users/register.html"

    def get(self, request):
        context = {
            "role_choices": User.ROLE_CHOICES,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        try:
            # Получаем данные из формы
            username = request.POST["username"]
            email = request.POST["email"]
            password = request.POST["password"]
            password_confirm = request.POST["password_confirm"]
            first_name = request.POST["first_name"]
            last_name = request.POST["last_name"]
            role = request.POST["role"]
            phone = request.POST.get("phone", "")

            # Проверяем совпадение паролей
            if password != password_confirm:
                messages.error(request, "Пароли не совпадают.")
                raise ValueError("Пароли не совпадают")

            # Проверяем уникальность username
            if User.objects.filter(username=username).exists():
                messages.error(request, "Пользователь с таким именем уже существует.")
                raise ValueError("Пользователь уже существует")

            # Проверяем уникальность email
            if User.objects.filter(email=email).exists():
                messages.error(request, "Пользователь с таким email уже существует.")
                raise ValueError("Email уже используется")

            # Создаем пользователя
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
                phone=phone,
            )

            messages.success(
                request, f"Пользователь {user.get_full_name()} успешно зарегистрирован."
            )

            # Автоматически авторизуем пользователя
            authenticated_user = authenticate(
                request, username=username, password=password
            )
            if authenticated_user:
                login(request, authenticated_user)

                # Перенаправляем в соответствующий кабинет
                if role == "translator":
                    return redirect("dashboards:translator_dashboard")
                elif role == "corrector":
                    return redirect("dashboards:corrector_dashboard")
                elif role in ["admin", "representative"]:
                    return redirect("dashboards:dashboard")
                else:
                    return redirect("dashboards:home")

        except Exception as e:
            # Если произошла ошибка, показываем форму снова
            pass

        context = {
            "role_choices": User.ROLE_CHOICES,
        }
        return render(request, self.template_name, context)


# Переименованные представления для обратной совместимости
login_view = LoginView.as_view()
logout_view = LogoutView.as_view()
register_view = RegisterView.as_view()

import logging
import os

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView, View

from translations.export_utils import export_user_report
from translations.models import Document, Sentence, Translation
from users.models import User

from .forms import UserForm
from .mixins import AdminOrRepresentativeMixin, CorrectorOnlyMixin, TranslatorOnlyMixin


class HomeView(View):
    """Главная страница - перенаправляет в соответствующий кабинет или на страницу входа"""

    def get(self, request):
        if request.user.is_authenticated:
            if request.user.role == "translator":
                return redirect("dashboards:translator_dashboard")
            elif request.user.role == "corrector":
                return redirect("dashboards:corrector_dashboard")
            elif request.user.role in ["admin", "representative"]:
                return redirect("dashboards:dashboard")
            else:
                return redirect("dashboards:dashboard")
        else:
            return redirect("users:login")


class DashboardView(LoginRequiredMixin, AdminOrRepresentativeMixin, TemplateView):
    """Главная страница кабинета представителя"""

    template_name = "dashboards/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Общая статистика
        context["total_users"] = User.objects.count()
        context["total_documents"] = Document.objects.count()
        context["total_sentences"] = Sentence.objects.count()
        context["total_translations"] = Translation.objects.count()

        # Статистика по статусам переводов
        context["approved_translations"] = Translation.objects.filter(status="approved").count()
        context["rejected_translations"] = Translation.objects.filter(status="rejected").count()
        context["pending_translations"] = Translation.objects.filter(status="pending").count()

        # Статистика по ролям пользователей
        context["users_by_role"] = User.objects.values("role").annotate(count=Count("id"))

        # Последние документы
        context["recent_documents"] = Document.objects.order_by("-uploaded_at")[:5]

        # Последние переводы
        context["recent_translations"] = Translation.objects.select_related(
            "sentence__document", "translator"
        ).order_by("-translated_at")[:5]

        return context


class UserListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список пользователей с возможностью поиска и фильтрации"""

    model = User
    template_name = "dashboards/user_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = User.objects.exclude(role="admin")

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query)
                | Q(last_name__icontains=search_query)
                | Q(email__icontains=search_query)
                | Q(username__icontains=search_query)
            )

        # Фильтр по роли
        role_filter = self.request.GET.get("role", "")
        if role_filter:
            queryset = queryset.filter(role=role_filter)

        # Сортировка
        sort_by = self.request.GET.get("sort", "first_name")
        if sort_by in ["first_name", "last_name", "email", "role", "date_joined"]:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["role_filter"] = self.request.GET.get("role", "")
        context["sort_by"] = self.request.GET.get("sort", "first_name")
        # Исключаем администраторов из списка ролей для фильтрации
        context["role_choices"] = [choice for choice in User.ROLE_CHOICES if choice[0] != "admin"]
        return context


class UserDetailView(LoginRequiredMixin, AdminOrRepresentativeMixin, DetailView):
    """Детальная информация о пользователе"""

    model = User
    template_name = "dashboards/user_detail.html"
    context_object_name = "user_obj"
    pk_url_kwarg = "user_id"

    def get_user_statistics(self, user_obj: User) -> dict:
        """
        Возвращает статистику по пользователю (слова, символы, предложения)
        """
        stats = {}

        if user_obj.role == "translator":
            # Получаем предложения, назначенные переводчику
            assigned_sentences = Sentence.objects.filter(assigned_to=user_obj)
            user_translations = Translation.objects.filter(translator=user_obj)

            # Статистика по оригинальным текстам (назначенные предложения)
            total_words = 0
            total_characters = 0
            total_characters_without_spaces = 0

            for sentence in assigned_sentences:
                # Подсчет слов (разделение по пробелам)
                words = sentence.original_text.split()
                total_words += len(words)

                # Подсчет символов с пробелами
                total_characters += len(sentence.original_text)

                # Подсчет символов без пробелов
                total_characters_without_spaces += len(sentence.original_text.replace(" ", ""))

            # Статистика по переводам
            total_translated_words = 0
            total_translated_characters = 0
            total_translated_characters_without_spaces = 0

            for translation in user_translations:
                if translation.translated_text:
                    # Подсчет слов в переводе
                    translated_words = translation.translated_text.split()
                    total_translated_words += len(translated_words)

                    # Подсчет символов в переводе
                    total_translated_characters += len(translation.translated_text)

                    # Подсчет символов без пробелов в переводе
                    total_translated_characters_without_spaces += len(translation.translated_text.replace(" ", ""))

            stats = {
                "total_sentences": assigned_sentences.count(),
                "translated_sentences": user_translations.count(),
                "total_words": total_words,
                "total_characters": total_characters,
                "total_characters_without_spaces": total_characters_without_spaces,
                "total_translated_words": total_translated_words,
                "total_translated_characters": total_translated_characters,
                "total_translated_characters_without_spaces": total_translated_characters_without_spaces,
            }

        elif user_obj.role == "corrector":
            # Получаем переводы, проверенные корректором
            user_corrections = Translation.objects.filter(sentence__corrector=user_obj)

            # Статистика по оригинальным текстам (предложения с проверенными переводами)
            total_words = 0
            total_characters = 0
            total_characters_without_spaces = 0

            for correction in user_corrections:
                sentence = correction.sentence
                # Подсчет слов (разделение по пробелам)
                words = sentence.original_text.split()
                total_words += len(words)

                # Подсчет символов с пробелами
                total_characters += len(sentence.original_text)

                # Подсчет символов без пробелов
                total_characters_without_spaces += len(sentence.original_text.replace(" ", ""))

            # Статистика по переводам
            total_translated_words = 0
            total_translated_characters = 0
            total_translated_characters_without_spaces = 0

            for correction in user_corrections:
                if correction.translated_text:
                    # Подсчет слов в переводе
                    translated_words = correction.translated_text.split()
                    total_translated_words += len(translated_words)

                    # Подсчет символов в переводе
                    total_translated_characters += len(correction.translated_text)

                    # Подсчет символов без пробелов в переводе
                    total_translated_characters_without_spaces += len(correction.translated_text.replace(" ", ""))

            stats = {
                "total_sentences": user_corrections.count(),
                "translated_sentences": user_corrections.count(),
                "total_words": total_words,
                "total_characters": total_characters,
                "total_characters_without_spaces": total_characters_without_spaces,
                "total_translated_words": total_translated_words,
                "total_translated_characters": total_translated_characters,
                "total_translated_characters_without_spaces": total_translated_characters_without_spaces,
            }

        elif user_obj.role in ["admin", "representative"]:
            # Получаем документы, загруженные пользователем
            user_documents = Document.objects.filter(uploaded_by=user_obj)

            # Статистика по всем предложениям в загруженных документах
            total_words = 0
            total_characters = 0
            total_characters_without_spaces = 0

            for document in user_documents:
                for sentence in document.sentences.all():
                    # Подсчет слов (разделение по пробелам)
                    words = sentence.original_text.split()
                    total_words += len(words)

                    # Подсчет символов с пробелами
                    total_characters += len(sentence.original_text)

                    # Подсчет символов без пробелов
                    total_characters_without_spaces += len(sentence.original_text.replace(" ", ""))

            # Статистика по переводам в загруженных документах
            total_translated_words = 0
            total_translated_characters = 0
            total_translated_characters_without_spaces = 0

            for document in user_documents:
                for sentence in document.sentences.filter(translation__isnull=False):
                    if sentence.translation and sentence.translation.translated_text:
                        # Подсчет слов в переводе
                        translated_words = sentence.translation.translated_text.split()
                        total_translated_words += len(translated_words)

                        # Подсчет символов в переводе
                        total_translated_characters += len(sentence.translation.translated_text)

                        # Подсчет символов без пробелов в переводе
                        total_translated_characters_without_spaces += len(
                            sentence.translation.translated_text.replace(" ", "")
                        )

            total_sentences = sum(doc.sentences.count() for doc in user_documents)
            translated_sentences = sum(
                doc.sentences.filter(translation__isnull=False).count() for doc in user_documents
            )

            stats = {
                "total_sentences": total_sentences,
                "translated_sentences": translated_sentences,
                "total_words": total_words,
                "total_characters": total_characters,
                "total_characters_without_spaces": total_characters_without_spaces,
                "total_translated_words": total_translated_words,
                "total_translated_characters": total_translated_characters,
                "total_translated_characters_without_spaces": total_translated_characters_without_spaces,
            }

        return stats

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_obj = self.object

        # Статистика пользователя
        context["user_documents"] = Document.objects.filter(uploaded_by=user_obj)
        context["user_sentences"] = Sentence.objects.filter(assigned_to=user_obj)
        context["user_translations"] = Translation.objects.filter(translator=user_obj)
        context["user_corrections"] = Translation.objects.filter(sentence__corrector=user_obj)

        # Статистика по статусам переводов
        user_translations = context["user_translations"]
        total_translations = user_translations.count()
        context["approved_count"] = user_translations.filter(status="approved").count()
        context["rejected_count"] = user_translations.filter(status="rejected").count()
        context["pending_count"] = user_translations.filter(status="pending").count()

        # Вычисление процентов
        if total_translations > 0:
            context["approved_percentage"] = round((context["approved_count"] / total_translations) * 100)
            context["rejected_percentage"] = round((context["rejected_count"] / total_translations) * 100)
            context["pending_percentage"] = round((context["pending_count"] / total_translations) * 100)
        else:
            context["approved_percentage"] = 0
            context["rejected_percentage"] = 0
            context["pending_percentage"] = 0

        # Инициализируем переменные по умолчанию
        context["total_assigned"] = 0
        context["pending_sentences"] = 0
        context["in_progress_sentences"] = 0
        context["translated_sentences"] = 0
        context["completed_sentences"] = 0
        context["total_completed"] = 0
        context["total_translated"] = 0
        context["total_rejected"] = 0
        context["total_reviewed"] = 0
        context["pending_corrections"] = 0
        context["completed_corrections"] = Translation.objects.none()

        # Дополнительная статистика для переводчиков
        if user_obj.role == "translator":
            assigned_sentences = Sentence.objects.filter(assigned_to=user_obj)
            context["total_assigned"] = assigned_sentences.count()
            context["pending_sentences"] = assigned_sentences.filter(status=0).count()
            context["in_progress_sentences"] = assigned_sentences.filter(status=0).count()
            context["translated_sentences"] = assigned_sentences.filter(status=1).count()
            context["completed_sentences"] = assigned_sentences.filter(status=2).count()
            context["total_completed"] = context["completed_sentences"]
            context["total_translated"] = context["translated_sentences"]
            context["total_rejected"] = user_translations.filter(status="rejected").count()

        # Дополнительная статистика для корректоров
        if user_obj.role == "corrector":
            # Переводы, которые нужно проверить (статус pending) и назначены этому корректору
            pending_corrections = Translation.objects.filter(
                Q(status="pending") & (Q(sentence__corrector=user_obj) | Q(sentence__corrector__isnull=True))
            )

            # Переводы, которые уже проверены этим корректором
            completed_corrections = Translation.objects.filter(
                sentence__corrector=user_obj, status__in=["approved", "rejected"]
            )

            context["total_reviewed"] = completed_corrections.count()
            context["pending_corrections"] = pending_corrections.count()
            context["completed_corrections"] = completed_corrections

            # Обновляем статистику по статусам для корректора
            context["approved_count"] = completed_corrections.filter(status="approved").count()
            context["rejected_count"] = completed_corrections.filter(status="rejected").count()

        # Добавляем статистику по словам и символам
        context["user_stats"] = self.get_user_statistics(user_obj)

        return context


class UserCreateView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Создание нового пользователя"""

    template_name = "dashboards/user_form.html"

    def get(self, request):
        form = UserForm()
        context = {
            "form": form,
            "user_obj": None,  # Изменяем имя переменной, чтобы не конфликтовать с request.user
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = UserForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f"Пользователь {user.get_full_name()} успешно создан.")
                return redirect("dashboards:user_detail", user_id=user.id)
            except Exception as e:
                messages.error(request, f"Ошибка при создании пользователя: {str(e)}")
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме.")

        context = {
            "form": form,
            "user_obj": None,  # Изменяем имя переменной, чтобы не конфликтовать с request.user
        }
        return render(request, self.template_name, context)


class UserEditView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Редактирование пользователя"""

    template_name = "dashboards/user_form.html"

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        form = UserForm(instance=user)
        context = {
            "form": form,
            "user": user,
        }
        return render(request, self.template_name, context)

    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        form = UserForm(request.POST, instance=user)

        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f"Пользователь {user.get_full_name()} успешно обновлен.")
                return redirect("dashboards:user_detail", user_id=user.id)
            except Exception as e:
                messages.error(request, f"Ошибка при обновлении пользователя: {str(e)}")
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме.")

        context = {
            "form": form,
            "user": user,
        }
        return render(request, self.template_name, context)


class UserDeleteView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Удаление пользователя"""

    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        if user == request.user:
            messages.error(request, "Вы не можете удалить свой собственный аккаунт.")
            return redirect("dashboards:user_list")

        try:
            user_name = user.get_full_name()
            user.delete()
            messages.success(request, f"Пользователь {user_name} успешно удален.")
        except Exception as e:
            messages.error(request, f"Ошибка при удалении пользователя: {str(e)}")

        return redirect("dashboards:user_list")


class UserStatisticsView(LoginRequiredMixin, AdminOrRepresentativeMixin, TemplateView):
    """Статистика конкретного пользователя"""

    template_name = "dashboards/user_statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = get_object_or_404(User, id=kwargs["user_id"])

        # Статистика переводов пользователя
        user_translations = Translation.objects.filter(translator=user)
        context["user"] = user
        context["total_translations"] = user_translations.count()
        context["approved_translations"] = user_translations.filter(status="approved").count()
        context["rejected_translations"] = user_translations.filter(status="rejected").count()
        context["pending_translations"] = user_translations.filter(status="pending").count()

        # Статистика по месяцам
        context["monthly_stats"] = (
            user_translations.extra(select={"month": "EXTRACT(month FROM translated_at)"})
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        return context


class TranslatorDashboardView(LoginRequiredMixin, TranslatorOnlyMixin, TemplateView):
    """Кабинет переводчика"""

    template_name = "dashboards/translator_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем предложения, назначенные переводчику
        assigned_sentences = Sentence.objects.filter(assigned_to=self.request.user)
        context["pending_sentences"] = assigned_sentences.filter(status=0)[:3]  # Не подтвержден
        context["in_progress_sentences"] = assigned_sentences.filter(status=0)[:3]  # Предложения в работе (не переведенные)
        context["translated_sentences"] = assigned_sentences.filter(
            status=1
        )[:3]  # Подтвердил переводчик (ожидает проверки)
        context["completed_sentences"] = assigned_sentences.filter(status=2)[:3]  # Подтвердил корректор

        # Получаем переводы пользователя
        user_translations = Translation.objects.filter(translator=self.request.user)
        context["recent_translations"] = user_translations.order_by("-translated_at")[:5]
        context["total_assigned"] = assigned_sentences.count()
        context["total_completed"] = context["completed_sentences"].count()
        context["total_translated"] = context["translated_sentences"].count()

        # Статистика по статусам переводов
        context["total_rejected"] = user_translations.filter(status="rejected").count()

        # Если нет назначенных предложений, показываем сообщение
        if not assigned_sentences.exists():
            messages.info(
                self.request,
                "Вам пока не назначены предложения для перевода. Ожидайте назначения от администратора.",
            )

        return context


class CorrectorDashboardView(LoginRequiredMixin, CorrectorOnlyMixin, TemplateView):
    """Кабинет корректора"""

    template_name = "dashboards/corrector_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Получаем переводы со статусом "pending", назначенные этому корректору или не назначенные никому
        # Корректор видит только переводы, где он указан как corrector или где corrector не указан
        context["in_review_translations"] = (
            Translation.objects.filter(translated_text__isnull=False)
            .exclude(translated_text="")
            .filter(status="pending")
            .filter(Q(sentence__corrector=self.request.user) | Q(sentence__corrector__isnull=True))
            .select_related("sentence__document", "translator")
            .order_by("-translated_at")[:3]
        )

        # Получаем переводы, которые нужно проверить (статус pending) и назначены этому корректору
        context["pending_corrections"] = Translation.objects.filter(
            Q(status="pending") & (Q(sentence__corrector=self.request.user) | Q(sentence__corrector__isnull=True))
        )

        # Получаем переводы, которые уже проверены этим корректором
        completed_corrections = Translation.objects.filter(
            sentence__corrector=self.request.user, status__in=["approved", "rejected"]
        )
        context["completed_corrections"] = completed_corrections.order_by("-corrected_at")[:3]

        # Статистика корректора
        context["total_reviewed"] = completed_corrections.count()
        context["approved_count"] = completed_corrections.filter(status="approved").count()
        context["rejected_count"] = completed_corrections.filter(status="rejected").count()
        context["pending_count"] = context["pending_corrections"].count()

        # Если нет переводов для проверки, показываем сообщение
        if not context["in_review_translations"].exists():
            messages.info(
                self.request,
                "Вам не назначены переводы для проверки. Ожидайте назначения от администратора.",
            )

        return context


class UserExportReportView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Экспорт отчета по конкретному пользователю"""

    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)

        # Получаем все необходимые данные для отчета
        user_detail_view = UserDetailView()
        user_detail_view.object = user
        context_data = user_detail_view.get_context_data()
        user_stats = user_detail_view.get_user_statistics(user)

        try:
            file_path = export_user_report(user, user_stats, context_data)

            # Проверяем, что файл существует
            if not os.path.exists(file_path):
                raise FileNotFoundError("Файл отчета не был создан")

            # Читаем файл и отправляем как ответ
            with open(file_path, "rb") as f:
                response = HttpResponse(
                    f.read(),
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                response["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'

            # Удаляем временный файл
            try:
                os.remove(file_path)
            except OSError:
                pass  # Игнорируем ошибки при удалении временного файла

            return response

        except Exception as e:
            import traceback

            logging.error(f"Ошибка при экспорте отчета: {str(e)}")
            logging.error(traceback.format_exc())
            messages.error(request, f"Ошибка при экспорте отчета: {str(e)}")
            return redirect("dashboards:user_detail", user_id=user_id)


# Переименованные представления для обратной совместимости
home = HomeView.as_view()
dashboard = DashboardView.as_view()
user_list = UserListView.as_view()
user_detail = UserDetailView.as_view()
user_create = UserCreateView.as_view()
user_edit = UserEditView.as_view()
user_delete = UserDeleteView.as_view()
user_statistics = UserStatisticsView.as_view()
translator_dashboard = TranslatorDashboardView.as_view()
corrector_dashboard = CorrectorDashboardView.as_view()
user_export_report = UserExportReportView.as_view()

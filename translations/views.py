from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse
from django.views.generic import View, ListView, DetailView
from django.db.models import Q
from django.core.files.storage import default_storage
from django.utils import timezone
import os
from .models import Document, Sentence, Translation
from .utils import extract_and_validate_sentences
from .export_utils import (
    export_document_translations,
    export_document_all_formats,
    get_document_statistics,
    export_sentences_to_csv,
)
from dashboards.mixins import AdminOrRepresentativeMixin
from .forms import (
    AssignTranslatorForm,
    AssignCorrectorForm,
    CreateTranslationForm,
    EditTranslationForm,
)


class DocumentListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список документов с поиском и фильтрацией"""

    model = Document
    template_name = "translations/document_list.html"
    context_object_name = "page_obj"
    paginate_by = 15

    def get_queryset(self):
        queryset = Document.objects.select_related("uploaded_by").all()

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(file__icontains=search_query)
                | Q(uploaded_by__first_name__icontains=search_query)
                | Q(uploaded_by__last_name__icontains=search_query)
            )

        # Фильтр по статусу обработки
        processed_filter = self.request.GET.get("processed", "")
        if processed_filter == "true":
            queryset = queryset.filter(is_processed=True)
        elif processed_filter == "false":
            queryset = queryset.filter(is_processed=False)

        # Сортировка
        sort_by = self.request.GET.get("sort", "-uploaded_at")
        if sort_by in [
            "file",
            "-file",
            "uploaded_at",
            "-uploaded_at",
            "uploaded_by__first_name",
        ]:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["processed_filter"] = self.request.GET.get("processed", "")
        context["sort_by"] = self.request.GET.get("sort", "-uploaded_at")
        return context


class DocumentUploadView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Загрузка нового документа"""

    template_name = "translations/document_upload.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        try:
            file = request.FILES.get("file")

            if not file:
                messages.error(request, "Пожалуйста, выберите файл для загрузки.")
                return render(request, self.template_name)

            # Проверяем, не был ли уже загружен этот файл
            existing_document = Document.objects.filter(
                file__endswith=file.name, uploaded_by=request.user
            ).first()

            if existing_document:
                messages.warning(
                    request, f'Документ "{file.name}" уже был загружен ранее.'
                )
                return redirect(
                    "translations:document_detail", document_id=existing_document.id
                )

            # Создаем документ
            document = Document.objects.create(file=file, uploaded_by=request.user)

            # Обрабатываем файл и извлекаем предложения
            file_path = document.file.path
            file_extension = os.path.splitext(file.name)[1]

            sentences_data = extract_and_validate_sentences(file_path, file_extension)

            # Проверяем, есть ли уже предложения для этого документа
            existing_sentences = Sentence.objects.filter(document=document).count()
            if existing_sentences > 0:
                # Если предложения уже существуют, удаляем их перед созданием новых
                Sentence.objects.filter(document=document).delete()

            # Создаем предложения
            for sentence_number, sentence_text in sentences_data:
                Sentence.objects.create(
                    document=document,
                    sentence_number=sentence_number,
                    original_text=sentence_text,
                )

            # Отмечаем документ как обработанный
            document.is_processed = True
            document.save()

            messages.success(
                request,
                f'Документ "{document.title}" успешно загружен. Извлечено {len(sentences_data)} предложений.',
            )
            return redirect("translations:document_detail", document_id=document.id)

        except Exception as e:
            # Если документ был создан, но произошла ошибка, удаляем его
            if "document" in locals():
                try:
                    if document.file:
                        default_storage.delete(document.file.name)
                    document.delete()
                except Exception:
                    pass

            messages.error(request, f"Ошибка при загрузке документа: {str(e)}")
            # Логируем ошибку для отладки
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f'Ошибка при загрузке документа {file.name if file else "Unknown"}: {str(e)}'
            )

        return render(request, self.template_name)


class DocumentDetailView(LoginRequiredMixin, AdminOrRepresentativeMixin, DetailView):
    """Детальная информация о документе"""

    model = Document
    template_name = "translations/document_detail.html"
    context_object_name = "document"
    pk_url_kwarg = "document_id"

    def get_queryset(self):
        return Document.objects.select_related("uploaded_by")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document = self.object

        # Получаем предложения с переводами и назначенными переводчиками
        sentences = document.sentences.select_related(
            "translation__translator", "corrector", "assigned_to"
        ).order_by("sentence_number")

        # Статистика документа
        context["stats"] = get_document_statistics(document)

        # Фильтрация предложений
        status_filter = self.request.GET.get("status", "")
        if status_filter:
            if status_filter in ["0", "1", "2", "3"]:
                sentences = sentences.filter(status=int(status_filter))

        # Поиск по тексту
        search_query = self.request.GET.get("search", "")
        if search_query:
            sentences = sentences.filter(
                Q(original_text__icontains=search_query)
                | Q(translation__translated_text__icontains=search_query)
                | Q(document__file__icontains=search_query)
            )

        # Пагинация
        from django.core.paginator import Paginator

        paginator = Paginator(sentences, 20)
        page_number = self.request.GET.get("page")
        context["page_obj"] = paginator.get_page(page_number)
        context["status_filter"] = status_filter
        context["search_query"] = search_query

        # Добавляем формы для массового назначения переводчиков и корректоров
        context["assign_form"] = AssignTranslatorForm()
        context["assign_corrector_form"] = AssignCorrectorForm()

        return context


class DocumentBulkAssignView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Массовое назначение переводчика и корректора для всех предложений документа"""

    def post(self, request, document_id):
        document = get_object_or_404(Document, id=document_id)
        translator_id = request.POST.get("assigned_to")
        corrector_id = request.POST.get("corrector")

        if not translator_id and not corrector_id:
            messages.error(request, "Не выбран ни переводчик, ни корректор.")
            return redirect("translations:document_detail", document_id=document_id)

        try:
            from users.models import User

            translator = None
            corrector = None

            if translator_id:
                translator = User.objects.get(id=translator_id, role="translator")

            if corrector_id:
                corrector = User.objects.get(id=corrector_id, role="corrector")

            sentences = Sentence.objects.filter(document=document)

            assigned_translator_count = 0
            assigned_corrector_count = 0

            for sentence in sentences:
                updated = False

                # Назначаем переводчика
                if translator and sentence.assigned_to != translator:
                    sentence.assigned_to = translator
                    updated = True
                    assigned_translator_count += 1

                # Назначаем корректора
                if corrector and sentence.corrector != corrector:
                    sentence.corrector = corrector
                    updated = True
                    assigned_corrector_count += 1

                if updated:
                    sentence.save()

            # Формируем сообщение об успехе
            success_messages = []
            if assigned_translator_count > 0:
                success_messages.append(
                    f"Переводчик {translator.get_full_name()} назначен для {assigned_translator_count} предложений"
                )
            if assigned_corrector_count > 0:
                success_messages.append(
                    f"Корректор {corrector.get_full_name()} назначен для {assigned_corrector_count} предложений"
                )

            if success_messages:
                messages.success(
                    request,
                    f'Документ "{document.title}": {", ".join(success_messages)}.',
                )
            else:
                messages.info(
                    request, "Все предложения уже назначены выбранным пользователям."
                )

        except User.DoesNotExist:
            messages.error(
                request, "Выбранный пользователь не найден или имеет неподходящую роль."
            )
        except Exception as e:
            messages.error(request, f"Ошибка при назначении: {str(e)}")

        return redirect("translations:document_detail", document_id=document_id)


class DocumentDeleteView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Удаление документа"""

    def post(self, request, document_id):
        document = get_object_or_404(Document, id=document_id)

        try:
            # Удаляем файл
            if document.file:
                default_storage.delete(document.file.name)

            document_title = document.title
            document.delete()
            messages.success(request, f'Документ "{document_title}" успешно удален.')
        except Exception as e:
            messages.error(request, f"Ошибка при удалении документа: {str(e)}")

        return redirect("translations:document_list")


class SentenceListView(LoginRequiredMixin, ListView):
    """Список предложений с фильтрацией - разные данные для разных ролей"""

    model = Sentence
    template_name = "translations/sentence_list.html"
    context_object_name = "page_obj"
    paginate_by = 25

    def get_queryset(self):
        # Базовый queryset с нужными связями
        queryset = Sentence.objects.select_related(
            "document",
            "assigned_to",
            "translation__translator",
            "corrector",
        )

        # Для переводчиков показываем только связанные предложения
        if self.request.user.role == "translator":
            queryset = queryset.filter(
                Q(assigned_to=self.request.user)  # Назначенные переводчику
                | Q(
                    translation__translator=self.request.user
                )  # Переведенные переводчиком
            ).distinct()
        # Для корректоров показываем предложения с переводами, назначенные этому корректору
        elif self.request.user.role == "corrector":
            queryset = queryset.filter(
                Q(translation__isnull=False)  # Только предложения с переводами
                & Q(corrector=self.request.user)  # Назначенные этому корректору
            )
        # Для админов и представителей показываем все предложения
        elif self.request.user.role in ["admin", "representative"]:
            queryset = queryset.all()
        else:
            # Для других ролей показываем пустой список
            queryset = queryset.none()

        # Фильтры для переводчиков
        if self.request.user.role == "translator":
            status_filter = self.request.GET.get("status", "")
            if status_filter:
                if status_filter == "assigned":
                    # Только назначенные, но без перевода
                    queryset = queryset.filter(
                        assigned_to=self.request.user, translation__isnull=True
                    )
                elif status_filter == "translated":
                    # С переводами
                    queryset = queryset.filter(
                        translation__translator=self.request.user
                    )
                elif status_filter == "approved":
                    # Утвержденные переводы
                    queryset = queryset.filter(
                        translation__translator=self.request.user,
                        translation__status="approved",
                    )
                elif status_filter == "rejected":
                    # Отклоненные переводы
                    queryset = queryset.filter(
                        translation__translator=self.request.user,
                        translation__status="rejected",
                    )
                elif status_filter == "pending":
                    # Ожидающие проверки переводы
                    queryset = queryset.filter(
                        translation__translator=self.request.user,
                        translation__status="pending",
                    )
                elif status_filter == "0":
                    queryset = queryset.filter(status=0)
                elif status_filter == "1":
                    queryset = queryset.filter(status=1)
                elif status_filter == "2":
                    queryset = queryset.filter(status=2)

        # Фильтры для корректоров
        elif self.request.user.role == "corrector":
            status_filter = self.request.GET.get("status", "")
            if status_filter:
                if status_filter == "pending":
                    # Ожидающие проверки переводы
                    queryset = queryset.filter(translation__status="pending")
                elif status_filter == "approved":
                    # Утвержденные переводы
                    queryset = queryset.filter(translation__status="approved")
                elif status_filter == "rejected":
                    # Отклоненные переводы
                    queryset = queryset.filter(translation__status="rejected")
        # Фильтры для админов и представителей
        else:
            status_filter = self.request.GET.get("status", "")
            if status_filter:
                if status_filter == "0":
                    queryset = queryset.filter(status=0)
                elif status_filter == "1":
                    queryset = queryset.filter(status=1)
                elif status_filter == "2":
                    queryset = queryset.filter(status=2)

            assigned_filter = self.request.GET.get("assigned", "")
            if assigned_filter == "assigned":
                queryset = queryset.filter(assigned_to__isnull=False)
            elif assigned_filter == "unassigned":
                queryset = queryset.filter(assigned_to__isnull=True)

        # Общие фильтры
        document_filter = self.request.GET.get("document", "")
        if document_filter:
            queryset = queryset.filter(document_id=document_filter)

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            if self.request.user.role == "translator":
                queryset = queryset.filter(
                    Q(original_text__icontains=search_query)
                    | Q(translation__translated_text__icontains=search_query)
                    | Q(document__file__icontains=search_query)
                )
            elif self.request.user.role == "corrector":
                queryset = queryset.filter(
                    Q(original_text__icontains=search_query)
                    | Q(translation__translated_text__icontains=search_query)
                    | Q(translation__translator__first_name__icontains=search_query)
                    | Q(translation__translator__last_name__icontains=search_query)
                )
            else:
                queryset = queryset.filter(
                    Q(original_text__icontains=search_query)
                    | Q(document__file__icontains=search_query)
                    | Q(assigned_to__first_name__icontains=search_query)
                    | Q(assigned_to__last_name__icontains=search_query)
                )

        # Сортировка
        if self.request.user.role == "translator":
            default_sort = "-created_at"
        elif self.request.user.role == "corrector":
            default_sort = "-created_at"
        else:
            default_sort = "document__file"

        sort_by = self.request.GET.get("sort", default_sort)
        if sort_by in [
            "sentence_number",
            "-sentence_number",
            "status",
            "-status",
            "created_at",
            "-created_at",
            "document__file",
            "-document__file",
        ]:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Статистика для переводчиков
        if self.request.user.role == "translator":
            user = self.request.user
            context["stats"] = {
                "assigned": Sentence.objects.filter(
                    assigned_to=user, translation__isnull=True
                ).count(),
                "translated": Translation.objects.filter(translator=user).count(),
                "approved": Translation.objects.filter(
                    translator=user, status="approved"
                ).count(),
                "rejected": Translation.objects.filter(
                    translator=user, status="rejected"
                ).count(),
                "pending": Translation.objects.filter(
                    translator=user, status="pending"
                ).count(),
            }
            context["documents"] = Document.objects.filter(
                sentences__assigned_to=user
            ).distinct()
        # Статистика для корректоров
        elif self.request.user.role == "corrector":
            user = self.request.user
            context["stats"] = {
                "total_with_translations": Sentence.objects.filter(
                    translation__isnull=False, corrector=user
                ).count(),
                "pending": Translation.objects.filter(
                    sentence__corrector=user, status="pending"
                ).count(),
                "approved": Translation.objects.filter(
                    sentence__corrector=user, status="approved"
                ).count(),
                "rejected": Translation.objects.filter(
                    sentence__corrector=user, status="rejected"
                ).count(),
            }
            context["documents"] = Document.objects.filter(
                sentences__translation__isnull=False, sentences__corrector=user
            ).distinct()
        else:
            context["documents"] = Document.objects.all()

        context["document_filter"] = self.request.GET.get("document", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["assigned_filter"] = self.request.GET.get("assigned", "")
        context["search_query"] = self.request.GET.get("search", "")
        if self.request.user.role == "translator":
            default_sort = "-created_at"
        elif self.request.user.role == "corrector":
            default_sort = "-created_at"
        else:
            default_sort = "document__file"
        context["sort_by"] = self.request.GET.get("sort", default_sort)
        return context


class SentenceDeleteView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Удаление предложения"""

    def post(self, request, sentence_id):
        sentence = get_object_or_404(Sentence, id=sentence_id)

        try:
            sentence_number = sentence.sentence_number
            document_title = sentence.document.title
            sentence.delete()
            messages.success(
                request,
                f'Предложение {sentence_number} из документа "{document_title}" успешно удалено.',
            )
        except Exception as e:
            messages.error(request, f"Ошибка при удалении предложения: {str(e)}")

        return redirect("translations:sentence_list")


class SentenceDetailView(LoginRequiredMixin, DetailView):
    """Просмотр одного предложения"""

    model = Sentence
    template_name = "translations/sentence_detail.html"
    context_object_name = "sentence"
    pk_url_kwarg = "sentence_id"

    def get_queryset(self):
        return Sentence.objects.select_related(
            "document",
            "assigned_to",
            "translation__translator",
            "corrector",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Для удобства добавим перевод, если есть
        context["translation"] = getattr(self.object, "translation", None)

        # Добавляем форму назначения переводчика для администраторов и представителей
        if self.request.user.role in ["admin", "representative"]:
            context["assign_form"] = AssignTranslatorForm(instance=self.object)

        # Добавляем форму назначения корректора для администраторов и представителей
        if self.request.user.role in ["admin", "representative"]:
            context["assign_corrector_form"] = AssignCorrectorForm()

        # Добавляем формы для переводчиков
        if self.request.user.role == "translator":
            # Добавляем форму создания перевода, если перевод еще не существует
            if not hasattr(self.object, "translation"):
                context["create_translation_form"] = CreateTranslationForm()
            # Добавляем форму редактирования перевода, если перевод существует и корректор еще не подтвердил
            elif hasattr(self.object, "translation") and self.object.status != 2:
                context["edit_translation_form"] = EditTranslationForm(
                    instance=self.object.translation
                )

        # Добавляем форму редактирования перевода для корректоров
        if (
            self.request.user.role == "corrector"
            and hasattr(self.object, "translation")
            and self.object.translation.status == "pending"
        ):
            context["edit_translation_form"] = EditTranslationForm(
                instance=self.object.translation
            )

        return context

    def post(self, request, sentence_id):
        """Обработка назначения переводчика и изменения статуса"""
        sentence = self.get_object()
        action = request.POST.get("action", "")

        # Обработка назначения переводчика (для админов и представителей)
        if action == "assign_translator":
            if request.user.role not in ["admin", "representative"]:
                messages.error(request, "У вас нет прав для назначения переводчиков.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            form = AssignTranslatorForm(request.POST, instance=sentence)

            if form.is_valid():
                old_assigned_to = sentence.assigned_to
                sentence = form.save()

                if sentence.assigned_to:
                    if old_assigned_to != sentence.assigned_to:
                        messages.success(
                            request,
                            f"Переводчик {sentence.assigned_to.get_full_name()} назначен для предложения №{sentence.sentence_number}",
                        )
                    else:
                        messages.info(
                            request, "Переводчик уже был назначен для этого предложения"
                        )
                else:
                    if old_assigned_to:
                        messages.success(
                            request,
                            f"Назначение переводчика снято с предложения №{sentence.sentence_number}",
                        )
                    else:
                        messages.info(
                            request, "Предложение не было назначено переводчику"
                        )
            else:
                messages.error(request, "Ошибка при назначении переводчика")

        # Обработка назначения корректора (для админов и представителей)
        elif action == "assign_corrector":
            if request.user.role not in ["admin", "representative"]:
                messages.error(request, "У вас нет прав для назначения корректоров.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            form = AssignCorrectorForm(request.POST)

            if form.is_valid():
                old_corrector = sentence.corrector
                new_corrector = form.cleaned_data.get("corrector")

                sentence.corrector = new_corrector
                sentence.save()

                if new_corrector:
                    if old_corrector != new_corrector:
                        messages.success(
                            request,
                            f"Корректор {new_corrector.get_full_name()} назначен для предложения №{sentence.sentence_number}",
                        )
                    else:
                        messages.info(
                            request, "Корректор уже был назначен для этого предложения"
                        )
                else:
                    if old_corrector:
                        messages.success(
                            request,
                            f"Назначение корректора снято с предложения №{sentence.sentence_number}",
                        )
                    else:
                        messages.info(
                            request, "Предложение не было назначено корректору"
                        )
            else:
                messages.error(request, "Ошибка при назначении корректора")

        # Обработка создания перевода (для переводчиков)
        elif action == "create_translation":
            if request.user.role != "translator":
                messages.error(request, "У вас нет прав для создания перевода.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            # Проверяем, что переводчик назначен на это предложение
            if sentence.assigned_to != request.user:
                messages.error(request, "Вы не назначены на это предложение.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            # Проверяем, что перевод еще не существует
            if hasattr(sentence, "translation"):
                messages.error(request, "Перевод для этого предложения уже существует.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            form = CreateTranslationForm(request.POST)

            if form.is_valid():
                translation = form.save(commit=False)
                translation.sentence = sentence
                translation.translator = request.user
                translation.save()

                # Автоматически изменяем статус предложения на "подтвердил переводчик"
                sentence.status = 1
                sentence.save()

                messages.success(
                    request,
                    f"Перевод для предложения №{sentence.sentence_number} успешно создан. Статус предложения изменен на 'подтвердил переводчик'.",
                )
            else:
                messages.error(
                    request, "Ошибка при создании перевода. Проверьте введенные данные."
                )

                # Обработка редактирования перевода (для переводчиков и корректоров)
        elif action == "edit_translation":
            if request.user.role not in ["translator", "corrector"]:
                messages.error(request, "У вас нет прав для редактирования перевода.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            # Проверяем, что перевод существует
            if not hasattr(sentence, "translation"):
                messages.error(request, "Перевод для этого предложения не найден.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            # Разные проверки для переводчика и корректора
            if request.user.role == "translator":
                # Проверяем, что переводчик назначен на это предложение
                if sentence.assigned_to != request.user:
                    messages.error(request, "Вы не назначены на это предложение.")
                    return redirect(
                        "translations:sentence_detail", sentence_id=sentence_id
                    )

                # Проверяем, что корректор еще не подтвердил предложение
                if sentence.status == 2:
                    messages.error(
                        request,
                        "Нельзя редактировать перевод после подтверждения корректором.",
                    )
                    return redirect(
                        "translations:sentence_detail", sentence_id=sentence_id
                    )

            elif request.user.role == "corrector":
                # Проверяем, что перевод находится в статусе "pending"
                if sentence.translation.status != "pending":
                    messages.error(
                        request,
                        "Можно редактировать только переводы в статусе 'на проверке'.",
                    )
                    return redirect(
                        "translations:sentence_detail", sentence_id=sentence_id
                    )

            form = EditTranslationForm(request.POST, instance=sentence.translation)

            if form.is_valid():
                translation = form.save()
                messages.success(
                    request,
                    f"Перевод для предложения №{sentence.sentence_number} успешно обновлен.",
                )
            else:
                messages.error(
                    request,
                    "Ошибка при обновлении перевода. Проверьте введенные данные.",
                )

        # Обработка проверки перевода (для корректоров)
        elif action == "review_translation":
            if request.user.role != "corrector":
                messages.error(request, "У вас нет прав для проверки переводов.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            # Проверяем, что перевод существует
            if not hasattr(sentence, "translation"):
                messages.error(request, "Перевод для этого предложения не найден.")
                return redirect("translations:sentence_detail", sentence_id=sentence_id)

            translation = sentence.translation
            review_action = request.POST.get("review_action", "")

            if review_action == "approve":
                translation.status = "approved"
                translation.corrector = request.user
                translation.corrected_at = timezone.now()
                translation.save()
                messages.success(
                    request,
                    f"Перевод для предложения №{sentence.sentence_number} одобрен.",
                )
            elif review_action == "reject":
                translation.status = "rejected"
                translation.corrected_at = timezone.now()
                translation.save()

                # Изменяем статус предложения обратно на "подтвердил переводчик"
                sentence.status = 1
                sentence.save()

                messages.success(
                    request,
                    f"Перевод для предложения №{sentence.sentence_number} отклонен. Статус предложения изменен на 'подтвердил переводчик'.",
                )
            else:
                messages.error(request, "Неверное действие проверки.")

        return redirect("translations:sentence_detail", sentence_id=sentence_id)


class TranslationListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список всех переводов"""

    model = Translation
    template_name = "translations/translation_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = Translation.objects.select_related(
            "sentence__document", "translator", "sentence__corrector"
        ).all()

        # Фильтры
        status_filter = self.request.GET.get("status", "")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        translator_filter = self.request.GET.get("translator", "")
        if translator_filter:
            queryset = queryset.filter(translator_id=translator_filter)

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(translated_text__icontains=search_query)
                | Q(sentence__original_text__icontains=search_query)
                | Q(translator__first_name__icontains=search_query)
                | Q(translator__last_name__icontains=search_query)
            )

        # Сортировка
        sort_by = self.request.GET.get("sort", "-translated_at")
        if sort_by in [
            "translated_at",
            "-translated_at",
            "status",
            "translator__first_name",
        ]:
            queryset = queryset.order_by(sort_by)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_filter"] = self.request.GET.get("status", "")
        context["translator_filter"] = self.request.GET.get("translator", "")
        context["search_query"] = self.request.GET.get("search", "")
        context["sort_by"] = self.request.GET.get("sort", "-translated_at")
        return context


class ApprovedTranslationsView(
    LoginRequiredMixin, AdminOrRepresentativeMixin, ListView
):
    """Переводы со статусом 'утверждено'"""

    model = Translation
    template_name = "translations/translation_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = Translation.objects.filter(status="approved").select_related(
            "sentence__document", "translator", "sentence__corrector"
        )

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(translated_text__icontains=search_query)
                | Q(sentence__original_text__icontains=search_query)
                | Q(sentence__document__file__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["status"] = "approved"
        return context


class RejectedTranslationsView(
    LoginRequiredMixin, AdminOrRepresentativeMixin, ListView
):
    """Переводы со статусом 'отклонено'"""

    model = Translation
    template_name = "translations/translation_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = Translation.objects.filter(status="rejected").select_related(
            "sentence__document", "translator", "sentence__corrector"
        )

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(translated_text__icontains=search_query)
                | Q(sentence__original_text__icontains=search_query)
                | Q(sentence__document__file__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["status"] = "rejected"
        return context


class PendingTranslationsView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Переводы со статусом 'на проверке'"""

    model = Translation
    template_name = "translations/translation_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = Translation.objects.filter(status="pending").select_related(
            "sentence__document", "translator", "sentence__corrector"
        )

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(translated_text__icontains=search_query)
                | Q(sentence__original_text__icontains=search_query)
                | Q(sentence__document__file__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("search", "")
        context["status"] = "pending"
        return context


class ExportDocumentView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Экспорт документа в различных форматах"""

    def get(self, request, document_id, format):
        document = get_object_or_404(Document, id=document_id)

        try:
            if format not in ["txt", "docx", "xlsx"]:
                messages.error(request, "Неподдерживаемый формат экспорта.")
                return redirect("translations:document_detail", document_id=document_id)

            file_path = export_document_translations(document, format)

            # Читаем файл и отправляем как ответ
            with open(file_path, "rb") as f:
                response = HttpResponse(
                    f.read(), content_type="application/octet-stream"
                )
                response["Content-Disposition"] = (
                    f'attachment; filename="{os.path.basename(file_path)}"'
                )

            # Удаляем временный файл
            os.remove(file_path)

            return response

        except Exception as e:
            messages.error(request, f"Ошибка при экспорте документа: {str(e)}")
            return redirect("translations:document_detail", document_id=document_id)


class ExportDocumentAllView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Экспорт документа во всех форматах в ZIP архиве"""

    def get(self, request, document_id):
        document = get_object_or_404(Document, id=document_id)

        try:
            file_path = export_document_all_formats(document)

            # Читаем файл и отправляем как ответ
            with open(file_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/zip")
                response["Content-Disposition"] = (
                    f'attachment; filename="{os.path.basename(file_path)}"'
                )

            # Удаляем временный файл
            os.remove(file_path)

            return response

        except Exception as e:
            messages.error(request, f"Ошибка при экспорте документа: {str(e)}")
            return redirect("translations:document_detail", document_id=document_id)


def export_sentences(request):
    """Экспорт предложений в CSV с учётом фильтров"""
    queryset = Sentence.objects.select_related(
        "document", "assigned_to", "translation__translator"
    ).all()
    document_filter = request.GET.get("document", "")
    if document_filter:
        queryset = queryset.filter(document_id=document_filter)
    status_filter = request.GET.get("status", "")
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    assigned_filter = request.GET.get("assigned", "")
    if assigned_filter == "assigned":
        queryset = queryset.filter(assigned_to__isnull=False)
    elif assigned_filter == "unassigned":
        queryset = queryset.filter(assigned_to__isnull=True)
    search_query = request.GET.get("search", "")
    if search_query:
        queryset = queryset.filter(
            Q(original_text__icontains=search_query)
            | Q(document__file__icontains=search_query)
            | Q(assigned_to__first_name__icontains=search_query)
            | Q(assigned_to__last_name__icontains=search_query)
        )
    sort_by = request.GET.get("sort", "document__file")
    allowed_sorts = [
        "document__file",
        "-document__file",
        "sentence_number",
        "-sentence_number",
        "status",
        "-status",
        "created_at",
        "-created_at",
    ]
    if sort_by in allowed_sorts:
        queryset = queryset.order_by(sort_by)
    return export_sentences_to_csv(queryset)


# Переименованные представления для обратной совместимости
document_list = DocumentListView.as_view()
document_upload = DocumentUploadView.as_view()
document_detail = DocumentDetailView.as_view()
document_bulk_assign = DocumentBulkAssignView.as_view()
document_delete = DocumentDeleteView.as_view()
sentence_list = SentenceListView.as_view()
sentence_delete = SentenceDeleteView.as_view()
sentence_detail = SentenceDetailView.as_view()
translation_list = TranslationListView.as_view()
approved_translations = ApprovedTranslationsView.as_view()
rejected_translations = RejectedTranslationsView.as_view()
pending_translations = PendingTranslationsView.as_view()
export_document = ExportDocumentView.as_view()
export_document_all = ExportDocumentAllView.as_view()

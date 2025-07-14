from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import HttpResponse
from django.views.generic import View, ListView, DetailView
from django.db.models import Q
from django.core.files.storage import default_storage
import os
from .models import Document, Sentence, Translation
from .utils import extract_and_validate_sentences
from .export_utils import (
    export_document_translations,
    get_document_statistics,
    export_sentences_to_csv,
)
from dashboards.mixins import AdminOrRepresentativeMixin
from .forms import AssignTranslatorForm


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
                except:
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
            "translation__translator", "translation__corrector", "assigned_to"
        ).order_by("sentence_number")

        # Статистика документа
        context["stats"] = get_document_statistics(document)

        # Фильтрация предложений
        status_filter = self.request.GET.get("status", "")
        if status_filter:
            if status_filter == "translated":
                sentences = sentences.filter(translation__isnull=False)
            elif status_filter == "not_translated":
                sentences = sentences.filter(translation__isnull=True)
            elif status_filter == "approved":
                sentences = sentences.filter(translation__status="approved")
            elif status_filter == "rejected":
                sentences = sentences.filter(translation__status="rejected")
            elif status_filter == "pending":
                sentences = sentences.filter(translation__status="pending")

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

        # Добавляем форму для массового назначения переводчиков
        context["assign_form"] = AssignTranslatorForm()

        return context


class DocumentBulkAssignTranslatorView(
    LoginRequiredMixin, AdminOrRepresentativeMixin, View
):
    """Массовое назначение переводчиков для предложений документа"""

    def post(self, request, document_id):
        document = get_object_or_404(Document, id=document_id)
        sentence_ids = request.POST.getlist("sentence_ids")
        translator_id = request.POST.get("assigned_to")

        if not sentence_ids:
            messages.error(request, "Не выбрано ни одного предложения.")
            return redirect("translations:document_detail", document_id=document_id)

        if not translator_id:
            messages.error(request, "Не выбран переводчик.")
            return redirect("translations:document_detail", document_id=document_id)

        try:
            from users.models import User

            translator = User.objects.get(id=translator_id, role="translator")
            sentences = Sentence.objects.filter(id__in=sentence_ids, document=document)

            assigned_count = 0
            for sentence in sentences:
                if sentence.assigned_to != translator:
                    sentence.assigned_to = translator
                    sentence.save()
                    assigned_count += 1

            if assigned_count > 0:
                messages.success(
                    request,
                    f'Переводчик {translator.get_full_name()} назначен для {assigned_count} предложений документа "{document.title}".',
                )
            else:
                messages.info(
                    request,
                    "Все выбранные предложения уже назначены этому переводчику.",
                )

        except User.DoesNotExist:
            messages.error(request, "Выбранный переводчик не найден.")
        except Exception as e:
            messages.error(request, f"Ошибка при назначении переводчика: {str(e)}")

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


class SentenceListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список всех предложений с фильтрацией"""

    model = Sentence
    template_name = "translations/sentence_list.html"
    context_object_name = "page_obj"
    paginate_by = 25

    def get_queryset(self):
        queryset = Sentence.objects.select_related(
            "document", "assigned_to", "translation__translator"
        ).all()

        # Фильтры
        document_filter = self.request.GET.get("document", "")
        if document_filter:
            queryset = queryset.filter(document_id=document_filter)

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

        # Поиск
        search_query = self.request.GET.get("search", "")
        if search_query:
            queryset = queryset.filter(
                Q(original_text__icontains=search_query)
                | Q(document__file__icontains=search_query)
                | Q(assigned_to__first_name__icontains=search_query)
                | Q(assigned_to__last_name__icontains=search_query)
            )

        # Сортировка
        sort_by = self.request.GET.get("sort", "document__file")
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
        context["documents"] = Document.objects.all()
        context["document_filter"] = self.request.GET.get("document", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["assigned_filter"] = self.request.GET.get("assigned", "")
        context["search_query"] = self.request.GET.get("search", "")
        context["sort_by"] = self.request.GET.get("sort", "document__file")
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
            "translation__corrector",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Для удобства добавим перевод, если есть
        context["translation"] = getattr(self.object, "translation", None)

        # Добавляем форму назначения переводчика для администраторов и представителей
        if self.request.user.role in ["admin", "representative"]:
            context["assign_form"] = AssignTranslatorForm(instance=self.object)

        return context

    def post(self, request, sentence_id):
        """Обработка назначения переводчика"""
        sentence = self.get_object()

        # Проверяем права доступа
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
                    messages.info(request, "Предложение не было назначено переводчику")
        else:
            messages.error(request, "Ошибка при назначении переводчика")

        return redirect("translations:sentence_detail", sentence_id=sentence_id)


class TranslationListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список всех переводов"""

    model = Translation
    template_name = "translations/translation_list.html"
    context_object_name = "page_obj"
    paginate_by = 20

    def get_queryset(self):
        queryset = Translation.objects.select_related(
            "sentence__document", "translator", "corrector"
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
            "sentence__document", "translator", "corrector"
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
            "sentence__document", "translator", "corrector"
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
            "sentence__document", "translator", "corrector"
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
document_bulk_assign_translator = DocumentBulkAssignTranslatorView.as_view()
document_delete = DocumentDeleteView.as_view()
sentence_list = SentenceListView.as_view()
sentence_delete = SentenceDeleteView.as_view()
sentence_detail = SentenceDetailView.as_view()
translation_list = TranslationListView.as_view()
approved_translations = ApprovedTranslationsView.as_view()
rejected_translations = RejectedTranslationsView.as_view()
pending_translations = PendingTranslationsView.as_view()
export_document = ExportDocumentView.as_view()

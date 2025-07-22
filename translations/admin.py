import os

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.html import format_html

from .export_utils import (
    export_document_all_formats,
    export_document_translations,
    get_document_statistics,
)
from .models import Document, Sentence, Translation, TranslationHistory


class TranslationInline(admin.TabularInline):
    """Инлайн для переводов в админке предложений"""

    model = Translation
    extra = 0
    readonly_fields = ["translated_at", "corrected_at"]
    fields = [
        "translated_text",
        "translator",
        "status",
        "translated_at",
        "corrected_at",
    ]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "translator":
            kwargs["queryset"] = db_field.related_model.objects.filter(role="translator")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TranslationHistoryInline(admin.TabularInline):
    """Инлайн для истории переводов"""

    model = TranslationHistory
    extra = 0
    readonly_fields = ["created_at"]
    fields = ["translated_text", "user", "action", "notes", "created_at"]
    can_delete = False
    max_num = 10  # Показываем только последние 10 записей


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "uploaded_by",
        "uploaded_at",
        "is_processed",
        "sentences_count",
        "completion_percentage",
    ]
    list_filter = ["is_processed", "uploaded_at", "uploaded_by__role"]
    search_fields = ["file", "uploaded_by__first_name", "uploaded_by__last_name"]
    readonly_fields = ["uploaded_at"]
    actions = [
        "export_selected_to_txt",
        "export_selected_to_docx",
        "export_selected_to_xlsx",
        "export_selected_all_formats",
    ]

    def sentences_count(self, obj):
        return obj.sentences.count()

    sentences_count.short_description = "Количество предложений"

    def completion_percentage(self, obj):
        stats = get_document_statistics(obj)
        return f"{stats['completion_percentage']}%"

    completion_percentage.short_description = "Процент завершения"

    def export_selected_to_txt(self, request, queryset):
        """Экспорт выбранных документов в TXT формат"""
        if len(queryset) == 1:
            document = queryset.first()
            try:
                file_path = export_document_translations(document, "txt")
                with open(file_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="application/octet-stream")
                    response["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'

                # Удаляем временный файл
                os.remove(file_path)
                return response
            except Exception as e:
                messages.error(request, f"Ошибка при экспорте: {str(e)}")
                return redirect("admin:translations_document_changelist")
        else:
            messages.warning(request, "Пожалуйста, выберите только один документ для экспорта в TXT.")
            return redirect("admin:translations_document_changelist")

    export_selected_to_txt.short_description = "Экспорт в TXT"

    def export_selected_to_docx(self, request, queryset):
        """Экспорт выбранных документов в DOCX формат"""
        if len(queryset) == 1:
            document = queryset.first()
            try:
                file_path = export_document_translations(document, "docx")
                with open(file_path, "rb") as f:
                    response = HttpResponse(
                        f.read(),
                        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                    response["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'

                # Удаляем временный файл
                os.remove(file_path)
                return response
            except Exception as e:
                messages.error(request, f"Ошибка при экспорте: {str(e)}")
                return redirect("admin:translations_document_changelist")
        else:
            messages.warning(
                request,
                "Пожалуйста, выберите только один документ для экспорта в DOCX.",
            )
            return redirect("admin:translations_document_changelist")

    export_selected_to_docx.short_description = "Экспорт в DOCX"

    def export_selected_to_xlsx(self, request, queryset):
        """Экспорт выбранных документов в XLSX формат"""
        if len(queryset) == 1:
            document = queryset.first()
            try:
                file_path = export_document_translations(document, "xlsx")
                with open(file_path, "rb") as f:
                    response = HttpResponse(
                        f.read(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    response["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'

                # Удаляем временный файл
                os.remove(file_path)
                return response
            except Exception as e:
                messages.error(request, f"Ошибка при экспорте: {str(e)}")
                return redirect("admin:translations_document_changelist")
        else:
            messages.warning(
                request,
                "Пожалуйста, выберите только один документ для экспорта в XLSX.",
            )
            return redirect("admin:translations_document_changelist")

    export_selected_to_xlsx.short_description = "Экспорт в XLSX"

    def export_selected_all_formats(self, request, queryset):
        """Экспорт выбранных документов во всех форматах в ZIP архиве"""
        if len(queryset) == 1:
            document = queryset.first()
            try:
                file_path = export_document_all_formats(document)
                with open(file_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="application/zip")
                    response["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'

                # Удаляем временный файл
                os.remove(file_path)
                return response
            except Exception as e:
                messages.error(request, f"Ошибка при экспорте: {str(e)}")
                return redirect("admin:translations_document_changelist")
        else:
            messages.warning(
                request,
                "Пожалуйста, выберите только один документ для экспорта во всех форматах.",
            )
            return redirect("admin:translations_document_changelist")

    export_selected_all_formats.short_description = "Экспорт во всех форматах (ZIP)"


@admin.register(Sentence)
class SentenceAdmin(admin.ModelAdmin):

    list_display = [
        "document",
        "sentence_number",
        "status",
        "assigned_to",
        "corrector",
        "has_translation_display",
        "created_at",
    ]
    list_filter = [
        "status",
        "document",
        "assigned_to__role",
        "assigned_to",
        "corrector__role",
        "corrector",
        "created_at",
    ]
    search_fields = [
        "original_text",
        "document__file",
        "assigned_to__first_name",
        "assigned_to__last_name",
        "corrector__first_name",
        "corrector__last_name",
    ]
    readonly_fields = ["created_at", "updated_at"]
    list_per_page = 50
    inlines = [TranslationInline]

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "document",
                    "sentence_number",
                    "original_text",
                    "status",
                    "assigned_to",
                    "corrector",
                )
            },
        ),
        ("Даты", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "assigned_to":
            kwargs["queryset"] = db_field.related_model.objects.filter(role="translator")
        elif db_field.name == "corrector":
            kwargs["queryset"] = db_field.related_model.objects.filter(role="corrector")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_translation_display(self, obj):
        if obj.has_translation:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')

    has_translation_display.short_description = "Есть перевод"


@admin.register(Translation)
class TranslationAdmin(admin.ModelAdmin):
    list_display = ["sentence", "translator", "status", "translated_at"]
    list_filter = [
        "status",
        "translated_at",
        "corrected_at",
        "translator__role",
    ]
    search_fields = [
        "translated_text",
        "sentence__original_text",
        "translator__first_name",
    ]
    readonly_fields = ["translated_at", "corrected_at"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "translator":
            kwargs["queryset"] = db_field.related_model.objects.filter(role="translator")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(TranslationHistory)
class TranslationHistoryAdmin(admin.ModelAdmin):
    list_display = ["translation", "user", "action", "created_at"]
    list_filter = ["action", "created_at", "user__role"]
    search_fields = ["translated_text", "notes", "user__first_name", "user__last_name"]
    readonly_fields = ["created_at"]
    list_per_page = 100

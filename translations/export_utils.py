import os
import shutil
from typing import Dict, List
import zipfile
import tempfile

import docx
import openpyxl
from django.core.files.storage import default_storage
import csv
from django.utils.encoding import smart_str
from django.http import HttpResponse

from .models import Document, Sentence, Translation


def export_to_txt(document: Document, output_path: str) -> str:
    """
    Экспортирует переводы документа в TXT файл
    """
    sentences = document.sentences.all().order_by("sentence_number")

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(f"Перевод документа: {document.title}\n")
        file.write("=" * 50 + "\n\n")

        for sentence in sentences:
            file.write(f"Предложение {sentence.sentence_number}:\n")
            file.write(f"Оригинал: {sentence.original_text}\n")

            if sentence.has_translation:
                translation = sentence.translation
                file.write(f"Перевод: {translation.translated_text}\n")
                file.write(
                    f"Статус: {'Одобрен' if translation.status == 'approved' else 'Отклонен' if translation.status == 'rejected' else 'На проверке'}\n"
                )
            else:
                file.write("Перевод: Не переведено\n")

            file.write("-" * 30 + "\n\n")

    return output_path


def export_to_docx(document: Document, output_path: str) -> str:
    """
    Экспортирует переводы документа в DOCX файл
    """
    doc = docx.Document()

    # Заголовок
    title = doc.add_heading(f"Перевод документа: {document.title}", 0)
    doc.add_paragraph("=" * 50)
    doc.add_paragraph()

    sentences = document.sentences.all().order_by("sentence_number")

    for sentence in sentences:
        # Номер предложения
        doc.add_heading(f"Предложение {sentence.sentence_number}", level=1)

        # Оригинал
        doc.add_paragraph("Оригинал:", style="Heading 2")
        doc.add_paragraph(sentence.original_text)

        # Перевод
        doc.add_paragraph("Перевод:", style="Heading 2")
        if sentence.has_translation:
            translation = sentence.translation
            doc.add_paragraph(translation.translated_text)

            # Статус
            status_text = (
                "Одобрен"
                if translation.status == "approved"
                else "Отклонен" if translation.status == "rejected" else "На проверке"
            )
            doc.add_paragraph(f"Статус: {status_text}")
        else:
            doc.add_paragraph("Не переведено")

        doc.add_paragraph()

    doc.save(output_path)
    return output_path


def export_to_xlsx(document: Document, output_path: str) -> str:
    """
    Экспортирует переводы документа в XLSX файл
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Переводы"

    # Заголовки
    headers = [
        "Номер предложения",
        "Оригинальный текст",
        "Переведенный текст",
        "Переводчик",
        "Корректор",
        "Статус",
        "Дата перевода",
        "Дата корректировки",
    ]

    for col, header in enumerate(headers, 1):
        sheet.cell(row=1, column=col, value=header)

    # Данные
    sentences = document.sentences.all().order_by("sentence_number")

    for row, sentence in enumerate(sentences, 2):
        sheet.cell(row=row, column=1, value=sentence.sentence_number)
        sheet.cell(row=row, column=2, value=sentence.original_text)

        if sentence.has_translation:
            translation = sentence.translation
            sheet.cell(row=row, column=3, value=translation.translated_text)
            sheet.cell(row=row, column=4, value=str(translation.translator))
            sheet.cell(
                row=row,
                column=5,
                value=str(sentence.corrector) if sentence.corrector else "",
            )

            # Статус
            if translation.status == "approved":
                status = "Одобрен"
            elif translation.status == "rejected":
                status = "Отклонен"
            else:
                status = "На проверке"
            sheet.cell(row=row, column=6, value=status)
            sheet.cell(
                row=row,
                column=7,
                value=translation.translated_at.strftime("%Y-%m-%d %H:%M"),
            )
            sheet.cell(
                row=row,
                column=8,
                value=(
                    translation.corrected_at.strftime("%Y-%m-%d %H:%M")
                    if translation.corrected_at
                    else ""
                ),
            )
        else:
            sheet.cell(row=row, column=3, value="Не переведено")

    # Автоматическая ширина столбцов
    for column in sheet.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        sheet.column_dimensions[column_letter].width = adjusted_width

    workbook.save(output_path)
    return output_path


def export_document_translations(document: Document, format_type: str) -> str:
    """
    Основная функция для экспорта переводов документа
    """
    # Создаем папку для экспорта, если её нет
    export_dir = os.path.join(default_storage.location, "exports")
    os.makedirs(export_dir, exist_ok=True)

    # Генерируем имя файла
    base_name = f"translation_{document.id}_{document.title.replace(' ', '_')}"

    if format_type == "txt":
        output_path = os.path.join(export_dir, f"{base_name}.txt")
        return export_to_txt(document, output_path)
    elif format_type == "docx":
        output_path = os.path.join(export_dir, f"{base_name}.docx")
        return export_to_docx(document, output_path)
    elif format_type == "xlsx":
        output_path = os.path.join(export_dir, f"{base_name}.xlsx")
        return export_to_xlsx(document, output_path)
    else:
        raise ValueError(f"Неподдерживаемый формат экспорта: {format_type}")


def export_document_all_formats(document: Document) -> str:
    """
    Экспортирует документ во всех поддерживаемых форматах и упаковывает в ZIP архив
    """
    # Создаем временную директорию для файлов
    with tempfile.TemporaryDirectory() as temp_dir:
        # Генерируем базовое имя файла
        base_name = f"translation_{document.id}_{document.title.replace(' ', '_')}"

        # Экспортируем во все форматы
        txt_path = os.path.join(temp_dir, f"{base_name}.txt")
        docx_path = os.path.join(temp_dir, f"{base_name}.docx")
        xlsx_path = os.path.join(temp_dir, f"{base_name}.xlsx")

        # Создаем файлы
        export_to_txt(document, txt_path)
        export_to_docx(document, docx_path)
        export_to_xlsx(document, xlsx_path)

        # Создаем ZIP архив
        zip_path = os.path.join(temp_dir, f"{base_name}_all_formats.zip")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Добавляем файлы в архив
            zipf.write(txt_path, os.path.basename(txt_path))
            zipf.write(docx_path, os.path.basename(docx_path))
            zipf.write(xlsx_path, os.path.basename(xlsx_path))

        # Копируем архив в постоянную директорию
        export_dir = os.path.join(default_storage.location, "exports")
        os.makedirs(export_dir, exist_ok=True)

        final_zip_path = os.path.join(export_dir, f"{base_name}_all_formats.zip")

        # Копируем файл
        shutil.copy2(zip_path, final_zip_path)

        return final_zip_path


def get_document_statistics(document: Document) -> Dict:
    """
    Возвращает статистику по документу
    """
    total_sentences = document.sentences.count()
    translated_sentences = document.sentences.filter(translation__isnull=False).count()
    approved_sentences = document.sentences.filter(
        translation__status="approved"
    ).count()
    rejected_sentences = document.sentences.filter(
        translation__status="rejected"
    ).count()
    pending_sentences = document.sentences.filter(translation__status="pending").count()

    # Статистика по словам и знакам в предложениях
    sentences = document.sentences.all()
    total_words = 0
    total_characters = 0
    total_characters_without_spaces = 0

    for sentence in sentences:
        # Подсчет слов (разделение по пробелам)
        words = sentence.original_text.split()
        total_words += len(words)

        # Подсчет символов с пробелами
        total_characters += len(sentence.original_text)

        # Подсчет символов без пробелов
        total_characters_without_spaces += len(sentence.original_text.replace(" ", ""))

    # Статистика по словам и знакам в переводах
    translations = document.sentences.filter(translation__isnull=False)
    total_translated_words = 0
    total_translated_characters = 0
    total_translated_characters_without_spaces = 0

    for sentence in translations:
        if sentence.translation:
            # Подсчет слов в переводе
            translated_words = sentence.translation.translated_text.split()
            total_translated_words += len(translated_words)

            # Подсчет символов в переводе
            total_translated_characters += len(sentence.translation.translated_text)

            # Подсчет символов без пробелов в переводе
            total_translated_characters_without_spaces += len(
                sentence.translation.translated_text.replace(" ", "")
            )

    # Средние показатели
    average_words_per_sentence = (
        total_words / total_sentences if total_sentences > 0 else 0
    )
    average_characters_per_sentence = (
        total_characters / total_sentences if total_sentences > 0 else 0
    )
    average_translated_words_per_translation = (
        total_translated_words / translated_sentences if translated_sentences > 0 else 0
    )
    average_translated_characters_per_translation = (
        total_translated_characters / translated_sentences
        if translated_sentences > 0
        else 0
    )

    return {
        "total_sentences": total_sentences,
        "translated_sentences": translated_sentences,
        "approved_sentences": approved_sentences,
        "rejected_sentences": rejected_sentences,
        "pending_sentences": pending_sentences,
        "total_words": total_words,
        "total_characters": total_characters,
        "total_characters_without_spaces": total_characters_without_spaces,
        "total_translated_words": total_translated_words,
        "total_translated_characters": total_translated_characters,
        "total_translated_characters_without_spaces": total_translated_characters_without_spaces,
        "average_words_per_sentence": round(average_words_per_sentence, 1),
        "average_characters_per_sentence": round(average_characters_per_sentence, 1),
        "average_translated_words_per_translation": round(
            average_translated_words_per_translation, 1
        ),
        "average_translated_characters_per_translation": round(
            average_translated_characters_per_translation, 1
        ),
        "completion_percentage": round(
            (
                (translated_sentences / total_sentences * 100)
                if total_sentences > 0
                else 0
            ),
            2,
        ),
        "approval_percentage": round(
            (approved_sentences / total_sentences * 100) if total_sentences > 0 else 0,
            2,
        ),
    }


def export_sentences_to_csv(queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=sentences.csv"
    writer = csv.writer(response)
    writer.writerow(
        [
            "Документ",
            "№ предложения",
            "Оригинальный текст",
            "Статус",
            "Назначено",
            "Перевод",
            "Дата создания",
            "Дата обновления",
        ]
    )
    for s in queryset:
        writer.writerow(
            [
                smart_str(s.document.title),
                s.sentence_number,
                smart_str(s.original_text),
                s.get_status_display(),
                smart_str(s.assigned_to.get_full_name() if s.assigned_to else ""),
                smart_str(
                    s.translation.translated_text if hasattr(s, "translation") else ""
                ),
                s.created_at.strftime("%d.%m.%Y %H:%M"),
                s.updated_at.strftime("%d.%m.%Y %H:%M"),
            ]
        )
    return response

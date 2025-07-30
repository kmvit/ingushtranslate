import os

from django.core.files.storage import default_storage
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Document, Sentence, Translation
from .utils import extract_and_validate_sentences


@receiver(post_save, sender=Translation)
def create_translation_history(sender, instance, created, **kwargs):
    """Создает запись в истории при создании или изменении перевода"""
    if created:
        # Новый перевод
        action = "translated"
        notes = ""
    else:
        # Изменение существующего перевода
        if instance.status == "approved":
            action = "approved"
            notes = ""
        elif instance.status == "rejected":
            action = "rejected"
            notes = ""
        else:
            action = "corrected"
            notes = ""

    # Определяем пользователя
    if action in ["approved", "rejected", "corrected"] and instance.sentence.corrector:
        user = instance.sentence.corrector
    else:
        user = instance.translator

    # Создаем запись в истории
    instance.history.create(
        translated_text=instance.translated_text,
        user=user,
        action=action,
        notes=notes or "",
    )


@receiver(post_save, sender=Document)
def process_document_sentences(sender, instance, created, **kwargs):
    """Обрабатывает загруженный документ и создает предложения"""
    if created and not instance.is_processed:
        try:
            # Получаем путь к файлу
            file_path = default_storage.path(instance.file.name)
            file_extension = os.path.splitext(instance.file.name)[1]

            # Извлекаем предложения из файла
            sentences_data = extract_and_validate_sentences(file_path, file_extension)

            # Создаем предложения в базе данных
            sentences_to_create = []
            for sentence_number, sentence_text in sentences_data:
                sentences_to_create.append(
                    Sentence(
                        document=instance,
                        original_text=sentence_text,
                        sentence_number=sentence_number,
                    )
                )

            # Массовое создание предложений
            if sentences_to_create:
                Sentence.objects.bulk_create(sentences_to_create)

            # Отмечаем документ как обработанный
            instance.is_processed = True
            instance.save(update_fields=["is_processed"])

        except Exception as e:
            # В случае ошибки логируем её (в продакшене лучше использовать proper logging)
            print(f"Ошибка при обработке документа {instance.id}: {str(e)}")
            # Можно также отправить уведомление администратору


@receiver(post_save, sender=Sentence)
def update_document_status_on_sentence_change(sender, instance, **kwargs):
    """Обновляет статус документа при изменении статуса предложения"""
    instance.document.update_status()


@receiver(post_save, sender=Translation)
def update_document_status_on_translation_change(sender, instance, **kwargs):
    """Обновляет статус документа при изменении перевода"""
    instance.sentence.document.update_status()

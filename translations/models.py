import os

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models


class Document(models.Model):
    """Модель для загруженных документов"""

    STATUS_CHOICES = [
        ("pending", "В обработке"),
        ("translated", "Переведен"),
        ("corrected", "Проверен"),
    ]

    file = models.FileField(
        upload_to="documents/",
        validators=[FileExtensionValidator(allowed_extensions=["txt", "docx", "xlsx"])],
        verbose_name="Файл",
    )
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Загрузил")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата загрузки")
    is_processed = models.BooleanField(default=False, verbose_name="Обработан")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус")
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translated_documents",
        verbose_name="Переводчик",
        limit_choices_to={"role": "translator"},
    )
    corrector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="corrected_documents",
        verbose_name="Корректор",
        limit_choices_to={"role": "corrector"},
    )

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return os.path.basename(self.file.name) if self.file else "Документ без файла"

    @property
    def title(self):
        """Возвращает название файла без расширения"""
        if self.file:
            filename = os.path.basename(self.file.name)
            return os.path.splitext(filename)[0]
        return "Документ без файла"

    def update_status(self):
        """Автоматически обновляет статус документа на основе статуса предложений"""
        sentences = self.sentences.all()
        
        if not sentences.exists():
            return
        
        total_sentences = sentences.count()
        approved_sentences = sentences.filter(status=2).count()  # Подтвердил корректор
        translated_sentences = sentences.filter(status__in=[1, 2]).count()  # Подтвердил переводчик или корректор
        
        if approved_sentences == total_sentences:
            # Все предложения утверждены корректором
            new_status = "corrected"
        elif translated_sentences == total_sentences:
            # Все предложения переведены
            new_status = "translated"
        else:
            # Документ еще в обработке
            new_status = "pending"
        
        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=['status'])


class Sentence(models.Model):
    """Модель для предложений из документов"""

    STATUS_CHOICES = [
        (0, "Не подтвержден"),
        (1, "Подтвердил переводчик"),
        (2, "Подтвердил корректор"),
        (3, "Отклонено корректором"),
    ]

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="sentences",
        verbose_name="Документ",
    )
    original_text = models.TextField(verbose_name="Оригинальный текст")
    sentence_number = models.PositiveIntegerField(verbose_name="Номер предложения")
    status = models.IntegerField(choices=STATUS_CHOICES, default=0, verbose_name="Статус")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_sentences",
        verbose_name="Назначено переводчику",
    )
    corrector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_corrections",
        verbose_name="Назначено корректору",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Предложение"
        verbose_name_plural = "Предложения"
        ordering = ["document", "sentence_number"]
        unique_together = ["document", "sentence_number"]

    def __str__(self):
        return f"{self.document.title} - Предложение {self.sentence_number}"

    @property
    def has_translation(self):
        """Проверяет, есть ли перевод для предложения"""
        return hasattr(self, "translation")

    @property
    def is_completed(self):
        """Проверяет, завершен ли перевод (статус 2)"""
        return self.status == 2

    @property
    def is_rejected(self):
        """Проверяет, отклонен ли перевод корректором (статус 3)"""
        return self.status == 3


class Translation(models.Model):
    """Модель для переводов предложений"""

    STATUS_CHOICES = [
        ("pending", "Ожидает проверки"),
        ("approved", "Утверждено"),
        ("rejected", "Отклонено"),
    ]
    sentence = models.OneToOneField(
        Sentence,
        on_delete=models.CASCADE,
        related_name="translation",
        verbose_name="Предложение",
    )
    translated_text = models.TextField(verbose_name="Переведенный текст")
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="translations",
        verbose_name="Переводчик",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Статус")
    translated_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата перевода")
    corrected_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата корректировки")

    class Meta:
        verbose_name = "Перевод"
        verbose_name_plural = "Переводы"
        ordering = ["-translated_at"]

    def __str__(self):
        return f"Перевод предложения {self.sentence.sentence_number}"

    def save(self, *args, **kwargs):
        # Обновляем статус предложения при сохранении перевода
        if self.status == "approved":
            self.sentence.status = 2
            self.sentence.save()
        elif self.status == "rejected":
            self.sentence.status = 3
            self.sentence.save()
        elif self.translated_text and self.status == "pending":
            self.sentence.status = 1
            self.sentence.save()
        super().save(*args, **kwargs)

    @property
    def is_approved(self):
        """Проверяет, одобрен ли перевод"""
        return self.status == "approved"

    @property
    def is_rejected(self):
        """Проверяет, отклонен ли перевод"""
        return self.status == "rejected"


class TranslationHistory(models.Model):
    """Модель для истории изменений переводов"""

    translation = models.ForeignKey(
        Translation,
        on_delete=models.CASCADE,
        related_name="history",
        verbose_name="Перевод",
    )
    translated_text = models.TextField(verbose_name="Текст перевода")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь")
    action = models.CharField(
        max_length=50, verbose_name="Действие"
    )  # 'translated', 'corrected', 'approved', 'rejected'
    notes = models.TextField(blank=True, verbose_name="Заметки")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата изменения")

    class Meta:
        verbose_name = "История перевода"
        verbose_name_plural = "История переводов"
        ordering = ["-created_at"]

    def __str__(self):
        return f"История перевода {self.translation.id} - {self.action}"

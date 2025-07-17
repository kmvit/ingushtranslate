from django import forms
from users.models import User
from .models import Sentence, Translation


class AssignTranslatorForm(forms.ModelForm):
    """Форма для назначения переводчика предложению"""

    class Meta:
        model = Sentence
        fields = ["assigned_to"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Получаем только пользователей с ролью переводчика
        translators = User.objects.filter(role="translator").order_by(
            "first_name", "last_name"
        )

        # Создаем выбор с пустым вариантом
        choices = [("", "Выберите переводчика...")]
        for translator in translators:
            display_name = translator.get_full_name() or translator.username
            choices.append((translator.id, display_name))

        self.fields["assigned_to"].choices = choices
        self.fields["assigned_to"].widget.attrs.update(
            {
                "class": "mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
            }
        )
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].empty_label = "Выберите переводчика..."


class AssignCorrectorForm(forms.Form):
    """Форма для назначения корректора переводу"""
    
    corrector = forms.ModelChoiceField(
        queryset=User.objects.filter(role="corrector").order_by("first_name", "last_name"),
        empty_label="Выберите корректора...",
        required=False,
        label="Корректор"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Получаем только пользователей с ролью корректора
        correctors = User.objects.filter(role="corrector").order_by(
            "first_name", "last_name"
        )

        # Создаем выбор с пустым вариантом
        choices = [("", "Выберите корректора...")]
        for corrector in correctors:
            display_name = corrector.get_full_name() or corrector.username
            choices.append((corrector.id, display_name))

        self.fields["corrector"].choices = choices
        self.fields["corrector"].widget.attrs.update(
            {
                "class": "mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
            }
        )


class ChangeSentenceStatusForm(forms.ModelForm):
    """Форма для изменения статуса предложения переводчиком"""

    class Meta:
        model = Sentence
        fields = ["status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ограничиваем выбор статусов для переводчика
        # Переводчик может только подтвердить перевод (статус 1)
        self.fields["status"].choices = [
            (0, "Не подтвержден"),
            (1, "Выполнить перевод"),
        ]

        self.fields["status"].widget.attrs.update(
            {
                "class": "mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
            }
        )


class CreateTranslationForm(forms.ModelForm):
    """Форма для создания перевода предложения"""

    class Meta:
        model = Translation
        fields = ["translated_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["translated_text"].widget = forms.Textarea(
            attrs={
                "class": "mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                "rows": 4,
                "placeholder": "Введите перевод предложения...",
            }
        )
        self.fields["translated_text"].label = "Перевод"
        self.fields["translated_text"].required = True


class EditTranslationForm(forms.ModelForm):
    """Форма для редактирования перевода предложения"""

    class Meta:
        model = Translation
        fields = ["translated_text"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["translated_text"].widget = forms.Textarea(
            attrs={
                "class": "mt-1 block w-full border-gray-300 rounded-md shadow-sm focus:ring-primary-500 focus:border-primary-500 sm:text-sm",
                "rows": 4,
                "placeholder": "Введите перевод предложения...",
            }
        )
        self.fields["translated_text"].label = "Перевод"
        self.fields["translated_text"].required = True

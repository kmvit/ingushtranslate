from django import forms
from users.models import User
from .models import Sentence


class AssignTranslatorForm(forms.ModelForm):
    """Форма для назначения переводчика предложению"""
    
    class Meta:
        model = Sentence
        fields = ['assigned_to']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Получаем только пользователей с ролью переводчика
        translators = User.objects.filter(role='translator').order_by('first_name', 'last_name')
        
        # Создаем выбор с пустым вариантом
        choices = [('', 'Выберите переводчика...')]
        for translator in translators:
            display_name = translator.get_full_name() or translator.username
            choices.append((translator.id, display_name))
        
        self.fields['assigned_to'].choices = choices
        self.fields['assigned_to'].widget.attrs.update({
            'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md'
        })
        self.fields['assigned_to'].required = False
        self.fields['assigned_to'].empty_label = "Выберите переводчика..." 
from django import forms
from users.models import User


class UserForm(forms.ModelForm):
    """Форма для создания и редактирования пользователей с ограниченным выбором ролей"""
    
    password = forms.CharField(
        widget=forms.PasswordInput(),
        required=False,
        help_text='Оставьте пустым, чтобы не менять пароль'
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(),
        required=False,
        help_text='Повторите пароль'
    )
    
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'phone', 'role']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Ограничиваем выбор ролей только переводчиком и корректором
        self.fields['role'].choices = [
            choice for choice in User.ROLE_CHOICES 
            if choice[0] in ['translator', 'corrector']
        ]
        
        # Добавляем CSS классы ко всем полям
        css_class = 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary-500 focus:border-primary-500'
        
        for field_name, field in self.fields.items():
            if field_name == 'password' or field_name == 'password_confirm':
                field.widget.attrs.update({
                    'class': css_class,
                    'placeholder': field.help_text
                })
            else:
                field.widget.attrs.update({
                    'class': css_class
                })
        
        # Если это редактирование существующего пользователя
        if self.instance and self.instance.pk:
            self.fields['username'].widget.attrs['readonly'] = True
            self.fields['username'].widget.attrs['class'] = css_class + ' bg-gray-100'
            self.fields['password'].help_text = 'Оставьте пустым, чтобы не менять пароль'
            self.fields['password_confirm'].help_text = 'Оставьте пустым, чтобы не менять пароль'
        else:
            # Для новых пользователей пароль обязателен
            self.fields['password'].required = True
            self.fields['password_confirm'].required = True
            self.fields['password'].help_text = 'Введите пароль'
            self.fields['password_confirm'].help_text = 'Повторите пароль'
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        
        # Проверяем совпадение паролей только если они введены
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Пароли не совпадают')
        
        # Для новых пользователей пароль обязателен
        if not self.instance.pk and not password:
            raise forms.ValidationError('Пароль обязателен для новых пользователей')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        
        # Устанавливаем пароль, если он был введен
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        
        if commit:
            user.save()
        return user 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import (
    View, TemplateView, ListView, DetailView
)
from django.db.models import Q, Count
from users.models import User
from translations.models import Document, Sentence, Translation
from datetime import datetime, timedelta
from .mixins import (
    AdminOrRepresentativeMixin, 
    TranslatorOnlyMixin, 
    CorrectorOnlyMixin
)
from .forms import UserForm


class HomeView(View):
    """Главная страница - перенаправляет в соответствующий кабинет или на страницу входа"""
    
    def get(self, request):
        if request.user.is_authenticated:
            if request.user.role == 'translator':
                return redirect('dashboards:translator_dashboard')
            elif request.user.role == 'corrector':
                return redirect('dashboards:corrector_dashboard')
            elif request.user.role in ['admin', 'representative']:
                return redirect('dashboards:dashboard')
            else:
                return redirect('dashboards:dashboard')
        else:
            return redirect('users:login')


class DashboardView(LoginRequiredMixin, AdminOrRepresentativeMixin, TemplateView):
    """Главная страница кабинета представителя"""
    template_name = 'dashboards/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Общая статистика
        context['total_users'] = User.objects.count()
        context['total_documents'] = Document.objects.count()
        context['total_sentences'] = Sentence.objects.count()
        context['total_translations'] = Translation.objects.count()
        
        # Статистика по статусам переводов
        context['approved_translations'] = Translation.objects.filter(status='approved').count()
        context['rejected_translations'] = Translation.objects.filter(status='rejected').count()
        context['pending_translations'] = Translation.objects.filter(status='pending').count()
        
        # Статистика по ролям пользователей
        context['users_by_role'] = User.objects.values('role').annotate(count=Count('id'))
        
        # Последние документы
        context['recent_documents'] = Document.objects.order_by('-uploaded_at')[:5]
        
        # Последние переводы
        context['recent_translations'] = Translation.objects.select_related(
            'sentence__document', 'translator'
        ).order_by('-translated_at')[:5]
        
        return context


class UserListView(LoginRequiredMixin, AdminOrRepresentativeMixin, ListView):
    """Список пользователей с возможностью поиска и фильтрации"""
    model = User
    template_name = 'dashboards/user_list.html'
    context_object_name = 'page_obj'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = User.objects.exclude(role='admin')
        
        # Поиск
        search_query = self.request.GET.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(username__icontains=search_query)
            )
        
        # Фильтр по роли
        role_filter = self.request.GET.get('role', '')
        if role_filter:
            queryset = queryset.filter(role=role_filter)
        
        # Сортировка
        sort_by = self.request.GET.get('sort', 'first_name')
        if sort_by in ['first_name', 'last_name', 'email', 'role', 'date_joined']:
            queryset = queryset.order_by(sort_by)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['role_filter'] = self.request.GET.get('role', '')
        context['sort_by'] = self.request.GET.get('sort', 'first_name')
        # Исключаем администраторов из списка ролей для фильтрации
        context['role_choices'] = [choice for choice in User.ROLE_CHOICES if choice[0] != 'admin']
        return context


class UserDetailView(LoginRequiredMixin, AdminOrRepresentativeMixin, DetailView):
    """Детальная информация о пользователе"""
    model = User
    template_name = 'dashboards/user_detail.html'
    context_object_name = 'user_obj'
    pk_url_kwarg = 'user_id'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_obj = self.object
        
        # Статистика пользователя
        context['user_documents'] = Document.objects.filter(uploaded_by=user_obj)
        context['user_sentences'] = Sentence.objects.filter(assigned_to=user_obj)
        context['user_translations'] = Translation.objects.filter(translator=user_obj)
        context['user_corrections'] = Translation.objects.filter(corrector=user_obj)
        
        # Статистика по статусам переводов
        user_translations = context['user_translations']
        total_translations = user_translations.count()
        context['approved_count'] = user_translations.filter(status='approved').count()
        context['rejected_count'] = user_translations.filter(status='rejected').count()
        context['pending_count'] = user_translations.filter(status='pending').count()
        
        # Вычисление процентов
        if total_translations > 0:
            context['approved_percentage'] = round((context['approved_count'] / total_translations) * 100)
            context['rejected_percentage'] = round((context['rejected_count'] / total_translations) * 100)
            context['pending_percentage'] = round((context['pending_count'] / total_translations) * 100)
        else:
            context['approved_percentage'] = 0
            context['rejected_percentage'] = 0
            context['pending_percentage'] = 0
        
        return context


class UserCreateView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Создание нового пользователя"""
    template_name = 'dashboards/user_form.html'
    
    def get(self, request):
        form = UserForm()
        context = {
            'form': form,
            'user': None,  # Явно указываем, что это создание
        }
        return render(request, self.template_name, context)
    
    def post(self, request):
        form = UserForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f'Пользователь {user.get_full_name()} успешно создан.')
                return redirect('dashboards:user_detail', user_id=user.id)
            except Exception as e:
                messages.error(request, f'Ошибка при создании пользователя: {str(e)}')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
            
        context = {
            'form': form,
            'user': None,  # Явно указываем, что это создание
        }
        return render(request, self.template_name, context)


class UserEditView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Редактирование пользователя"""
    template_name = 'dashboards/user_form.html'
    
    def get(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        form = UserForm(instance=user)
        context = {
            'form': form,
            'user': user,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        form = UserForm(request.POST, instance=user)
        
        if form.is_valid():
            try:
                user = form.save()
                messages.success(request, f'Пользователь {user.get_full_name()} успешно обновлен.')
                return redirect('dashboards:user_detail', user_id=user.id)
            except Exception as e:
                messages.error(request, f'Ошибка при обновлении пользователя: {str(e)}')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
        
        context = {
            'form': form,
            'user': user,
        }
        return render(request, self.template_name, context)


class UserDeleteView(LoginRequiredMixin, AdminOrRepresentativeMixin, View):
    """Удаление пользователя"""
    
    def post(self, request, user_id):
        user = get_object_or_404(User, id=user_id)
        
        if user == request.user:
            messages.error(request, 'Вы не можете удалить свой собственный аккаунт.')
            return redirect('dashboards:user_list')
        
        try:
            user_name = user.get_full_name()
            user.delete()
            messages.success(request, f'Пользователь {user_name} успешно удален.')
        except Exception as e:
            messages.error(request, f'Ошибка при удалении пользователя: {str(e)}')
        
        return redirect('dashboards:user_list')





class UserStatisticsView(LoginRequiredMixin, AdminOrRepresentativeMixin, TemplateView):
    """Статистика конкретного пользователя"""
    template_name = 'dashboards/user_statistics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = get_object_or_404(User, id=kwargs['user_id'])
        
        # Статистика переводов пользователя
        user_translations = Translation.objects.filter(translator=user)
        context['user'] = user
        context['total_translations'] = user_translations.count()
        context['approved_translations'] = user_translations.filter(status='approved').count()
        context['rejected_translations'] = user_translations.filter(status='rejected').count()
        context['pending_translations'] = user_translations.filter(status='pending').count()
        
        # Статистика по месяцам
        context['monthly_stats'] = user_translations.extra(
            select={'month': "EXTRACT(month FROM translated_at)"}
        ).values('month').annotate(count=Count('id')).order_by('month')
        
        return context


class TranslatorDashboardView(LoginRequiredMixin, TranslatorOnlyMixin, TemplateView):
    """Кабинет переводчика"""
    template_name = 'dashboards/translator_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Получаем предложения, назначенные переводчику
        assigned_sentences = Sentence.objects.filter(assigned_to=self.request.user)
        context['pending_sentences'] = assigned_sentences.filter(status=0)  # Не подтвержден
        context['in_progress_sentences'] = assigned_sentences.filter(status=1)  # Подтвердил переводчик
        context['completed_sentences'] = assigned_sentences.filter(status=2)  # Подтвердил корректор
        
        # Получаем переводы пользователя
        user_translations = Translation.objects.filter(translator=self.request.user)
        context['recent_translations'] = user_translations.order_by('-translated_at')[:5]
        context['total_assigned'] = assigned_sentences.count()
        context['total_completed'] = context['completed_sentences'].count()
        
        # Если нет назначенных предложений, показываем сообщение
        if not assigned_sentences.exists():
            messages.info(self.request, 'Вам пока не назначены предложения для перевода. Ожидайте назначения от администратора.')
        
        return context


class CorrectorDashboardView(LoginRequiredMixin, CorrectorOnlyMixin, TemplateView):
    """Кабинет корректора"""
    template_name = 'dashboards/corrector_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Получаем переводы, которые нужно проверить
        context['pending_corrections'] = Translation.objects.filter(status='pending')
        context['in_review_translations'] = Translation.objects.filter(
            corrector=self.request.user, status='pending'
        )
        completed_corrections = Translation.objects.filter(
            corrector=self.request.user, status__in=['approved', 'rejected']
        )
        context['completed_corrections'] = completed_corrections
        
        # Статистика корректора
        context['total_reviewed'] = completed_corrections.count()
        context['approved_count'] = completed_corrections.filter(status='approved').count()
        context['rejected_count'] = completed_corrections.filter(status='rejected').count()
        
        # Если нет переводов для проверки, показываем сообщение
        if (not context['pending_corrections'].exists() and 
            not context['in_review_translations'].exists()):
            messages.info(self.request, 'В данный момент нет переводов, требующих проверки. Ожидайте новых переводов от переводчиков.')
        
        return context


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

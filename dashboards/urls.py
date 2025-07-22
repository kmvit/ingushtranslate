from django.urls import path

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "translator/",
        views.TranslatorDashboardView.as_view(),
        name="translator_dashboard",
    ),
    path("corrector/", views.CorrectorDashboardView.as_view(), name="corrector_dashboard"),
    path(
        "statistics/user/<int:user_id>/",
        views.UserStatisticsView.as_view(),
        name="user_statistics",
    ),
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:user_id>/", views.UserDetailView.as_view(), name="user_detail"),
    path("users/<int:user_id>/edit/", views.UserEditView.as_view(), name="user_edit"),
    path(
        "users/<int:user_id>/delete/",
        views.UserDeleteView.as_view(),
        name="user_delete",
    ),
    path("users/create/", views.UserCreateView.as_view(), name="user_create"),
    path(
        "users/<int:user_id>/export/",
        views.UserExportReportView.as_view(),
        name="user_export_report",
    ),
]

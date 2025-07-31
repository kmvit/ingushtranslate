from django.urls import path

from . import views

app_name = "translations"

urlpatterns = [
    path("documents/", views.document_list, name="document_list"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:document_id>/", views.document_detail, name="document_detail"),
    path(
        "documents/<int:document_id>/bulk-assign-all/",
        views.document_bulk_assign,
        name="document_bulk_assign",
    ),
    path(
        "documents/<int:document_id>/delete/",
        views.document_delete,
        name="document_delete",
    ),
    path("sentences/", views.sentence_list, name="sentence_list"),
    path("sentences/<int:sentence_id>/", views.sentence_detail, name="sentence_detail"),
    path(
        "sentences/<int:sentence_id>/delete/",
        views.sentence_delete,
        name="sentence_delete",
    ),
    path(
        "sentence/<int:sentence_id>/update_translation/",
        views.update_sentence_translation,
        name="update_sentence_translation",
    ),
    path("sentences/export/", views.export_sentences, name="sentence_export"),
    path("translations/", views.translation_list, name="translation_list"),
    path(
        "translations/approved/",
        views.approved_translations,
        name="approved_translations",
    ),
    path(
        "translations/rejected/",
        views.rejected_translations,
        name="rejected_translations",
    ),
    path("translations/pending/", views.pending_translations, name="pending_translations"),
    path(
        "export/<int:document_id>/all/",
        views.export_document_all,
        name="export_document_all",
    ),
    path(
        "export/<int:document_id>/<str:format>/",
        views.export_document,
        name="export_document",
    ),
]

#!/usr/bin/env python3
"""
Скрипт для отладки переводов в базе данных
"""
import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ingushtranslate.settings')
django.setup()

from translations.models import Document, Sentence, Translation

def debug_translations():
    """Отлаживает переводы в базе данных"""
    
    # Получаем первый документ
    document = Document.objects.first()
    if not document:
        print("Нет документов в базе данных")
        return
    
    print(f"Документ: {document.title} (ID: {document.id})")
    print("=" * 50)
    
    # Получаем все предложения
    sentences = document.sentences.all().order_by("sentence_number")
    print(f"Всего предложений: {sentences.count()}")
    
    # Проверяем переводы
    translations_count = Translation.objects.filter(sentence__document=document).count()
    print(f"Всего записей переводов: {translations_count}")
    
    # Проверяем первые 10 предложений
    print("\nПервые 10 предложений:")
    print("-" * 50)
    
    for sentence in sentences[:10]:
        print(f"\nПредложение {sentence.sentence_number}:")
        print(f"  Оригинал: {sentence.original_text[:100]}...")
        
        # Проверяем has_translation
        has_translation = sentence.has_translation
        print(f"  has_translation: {has_translation}")
        
        # Проверяем атрибут translation
        has_attr = hasattr(sentence, 'translation')
        print(f"  hasattr('translation'): {has_attr}")
        
        # Проверяем объект перевода
        translation_obj = getattr(sentence, 'translation', None)
        print(f"  translation object: {translation_obj}")
        
        if translation_obj:
            print(f"  translated_text: '{translation_obj.translated_text[:100]}...'")
            print(f"  status: {translation_obj.status}")
            print(f"  translator: {translation_obj.translator}")
        else:
            print(f"  translated_text: None")
    
    # Проверяем все переводы для документа
    print(f"\nВсе переводы для документа:")
    print("-" * 50)
    
    translations = Translation.objects.filter(sentence__document=document).order_by('sentence__sentence_number')
    for translation in translations[:10]:  # Первые 10
        print(f"Предложение {translation.sentence.sentence_number}: '{translation.translated_text[:100]}...'")
    
    # Статистика
    print(f"\nСтатистика:")
    print("-" * 50)
    
    total_sentences = sentences.count()
    sentences_with_translations = sentences.filter(translation__isnull=False).count()
    translations_with_text = 0
    
    for sentence in sentences:
        if hasattr(sentence, 'translation') and sentence.translation and sentence.translation.translated_text:
            translations_with_text += 1
    
    print(f"Всего предложений: {total_sentences}")
    print(f"Предложений с переводами (по БД): {sentences_with_translations}")
    print(f"Предложений с текстом перевода: {translations_with_text}")

if __name__ == "__main__":
    debug_translations()

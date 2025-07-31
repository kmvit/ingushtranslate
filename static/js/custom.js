function toggleExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.classList.toggle('hidden');
}

// Закрыть меню при клике вне его
document.addEventListener('click', function(event) {
    const menu = document.getElementById('exportMenu');
    const button = event.target.closest('button');
    if (!button || !button.onclick) {
        menu.classList.add('hidden');
    }
});

    // Установка ширины прогресс-баров с анимацией
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            const translateProgressBar = document.querySelector('.progress-bar-translate');
            const correctProgressBar = document.querySelector('.progress-bar-correct');
            
            if (translateProgressBar) {
                const completionPercentage = parseFloat(translateProgressBar.getAttribute('data-percentage'));
                // Минимальная видимая ширина для очень маленьких процентов
                const minWidth = completionPercentage > 0 && completionPercentage < 1 ? 1 : completionPercentage;
                translateProgressBar.style.width = minWidth + '%';
            }
            
            if (correctProgressBar) {
                const approvalPercentage = parseFloat(correctProgressBar.getAttribute('data-percentage'));
                // Минимальная видимая ширина для очень маленьких процентов
                const minWidth = approvalPercentage > 0 && approvalPercentage < 1 ? 1 : approvalPercentage;
                correctProgressBar.style.width = minWidth + '%';
            }
        }, 100);
        
        // Выделяем первое предложение без перевода при загрузке страницы
        highlightFirstUntranslatedSentence();

    // Обработка редактирования переводов
    const textareas = document.querySelectorAll('textarea[data-sentence-id]');
    const saveButtons = document.querySelectorAll('.save-translation-btn');
    
    // Показывать кнопку сохранения при изменении текста и обработка Ctrl+Enter
    textareas.forEach(function(textarea) {
        const sentenceId = textarea.getAttribute('data-sentence-id');
        const saveBtn = document.querySelector(`.save-translation-btn[data-sentence-id="${sentenceId}"]`);
        const originalValue = textarea.value;
        
        textarea.addEventListener('input', function() {
            if (textarea.value !== originalValue) {
                saveBtn.style.display = 'inline-flex';
            } else {
                saveBtn.style.display = 'none';
            }
        });
        
        // Обработка Ctrl+Enter для сохранения
        textarea.addEventListener('keydown', function(event) {
            if (event.ctrlKey && event.key === 'Enter') {
                event.preventDefault(); // Предотвращаем перенос строки
                if (saveBtn.style.display !== 'none') {
                    saveBtn.click(); // Эмулируем клик по кнопке сохранения
                }
            }
            // Обработка Enter для сохранения и перехода к следующему предложению
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault(); // Предотвращаем перенос строки
                if (saveBtn.style.display !== 'none') {
                    saveBtn.click(); // Эмулируем клик по кнопке сохранения
                }
            }
        });
    });
    
    // Обработка сохранения переводов
    saveButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const sentenceId = button.getAttribute('data-sentence-id');
            const textarea = document.querySelector(`textarea[data-sentence-id="${sentenceId}"]`);
            const translatedText = textarea.value.trim();
            
            // Показывать индикатор загрузки
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>Сохранение...';
            
            // Отправка данных на сервер
            fetch(`/translations/sentence/${sentenceId}/update_translation/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify({
                    translated_text: translatedText
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Скрыть кнопку сохранения
                    button.style.display = 'none';
                    // Показать уведомление об успехе
                    showNotification(data.message, 'success');
                    
                    // Обновляем статус предложения в таблице
                    updateSentenceStatus(sentenceId, data.sentence_status, data.sentence_status_display);
                    
                    // Переходим к следующему предложению
                    moveToNextSentence(sentenceId);
                } else {
                    showNotification('Ошибка при сохранении: ' + data.error, 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showNotification('Ошибка при сохранении перевода', 'error');
            })
            .finally(() => {
                // Восстановить кнопку
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-save mr-1"></i>Сохранить';
            });
        });
    });
});

// Функция для показа уведомлений
function showNotification(message, type) {
    // Создаем элемент уведомления
    const notification = document.createElement('div');
    let bgColor, textColor, icon;
    
    switch (type) {
        case 'success':
            bgColor = 'bg-green-500';
            textColor = 'text-white';
            icon = 'fa-check-circle';
            break;
        case 'error':
            bgColor = 'bg-red-500';
            textColor = 'text-white';
            icon = 'fa-exclamation-circle';
            break;
        case 'info':
            bgColor = 'bg-blue-500';
            textColor = 'text-white';
            icon = 'fa-info-circle';
            break;
        default:
            bgColor = 'bg-gray-500';
            textColor = 'text-white';
            icon = 'fa-info-circle';
    }
    
    notification.className = `fixed top-4 right-4 z-50 px-6 py-4 rounded-md shadow-lg ${bgColor} ${textColor}`;
    notification.innerHTML = `
        <div class="flex items-center">
            <i class="fas ${icon} mr-2"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Удаляем уведомление через 3 секунды
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Функция для обновления статуса предложения в таблице
function updateSentenceStatus(sentenceId, status, statusDisplay) {
    const statusCell = document.querySelector(`tr[data-sentence-id="${sentenceId}"] .status-cell`);
    if (statusCell) {
        let statusHtml = '';
        let statusClass = '';
        
        switch (status) {
            case 0:
                statusHtml = '<i class="fas fa-minus mr-1"></i>Не подтвержден';
                statusClass = 'bg-gray-100 text-gray-800';
                break;
            case 1:
                statusHtml = '<i class="fas fa-user-check mr-1"></i>Подтвердил переводчик';
                statusClass = 'bg-blue-100 text-blue-800';
                break;
            case 2:
                statusHtml = '<i class="fas fa-check mr-1"></i>Подтвердил корректор';
                statusClass = 'bg-green-100 text-green-800';
                break;
            case 3:
                statusHtml = '<i class="fas fa-times mr-1"></i>Отклонено корректором';
                statusClass = 'bg-red-100 text-red-800';
                break;
        }
        
        statusCell.innerHTML = `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusClass}">${statusHtml}</span>`;
    }
}

// Функция для выделения первого непереведенного предложения
function highlightFirstUntranslatedSentence() {
    const sentenceRows = document.querySelectorAll('tr[data-sentence-id]');
    
    for (let i = 0; i < sentenceRows.length; i++) {
        const row = sentenceRows[i];
        const statusCell = row.querySelector('.status-cell');
        
        // Проверяем, есть ли перевод (статус 0 - не подтвержден)
        if (statusCell && statusCell.textContent.includes('Не подтвержден')) {
            // Добавляем выделение к первому непереведенному предложению
            row.classList.add('bg-blue-50', 'border-l-4', 'border-blue-500');
            
            // Прокручиваем к нему
            row.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'center' 
            });
            
            // Фокусируемся на текстовом поле
            const textarea = row.querySelector('textarea[data-sentence-id]');
            if (textarea) {
                textarea.focus();
            }
            
            break;
        }
    }
}

// Функция для перехода к следующему предложению
function moveToNextSentence(currentSentenceId) {
    // Получаем все строки с предложениями
    const sentenceRows = document.querySelectorAll('tr[data-sentence-id]');
    let currentIndex = -1;
    
    // Находим индекс текущего предложения
    for (let i = 0; i < sentenceRows.length; i++) {
        if (sentenceRows[i].getAttribute('data-sentence-id') === currentSentenceId) {
            currentIndex = i;
            break;
        }
    }
    
    // Если нашли текущее предложение и есть следующее
    if (currentIndex !== -1 && currentIndex < sentenceRows.length - 1) {
        const nextRow = sentenceRows[currentIndex + 1];
        const nextSentenceId = nextRow.getAttribute('data-sentence-id');
        
        // Убираем выделение с текущего предложения
        sentenceRows[currentIndex].classList.remove('bg-blue-50', 'border-l-4', 'border-blue-500');
        
        // Добавляем выделение к следующему предложению
        nextRow.classList.add('bg-blue-50', 'border-l-4', 'border-blue-500');
        
        // Прокручиваем к следующему предложению
        nextRow.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
        
        // Фокусируемся на текстовом поле следующего предложения
        const nextTextarea = nextRow.querySelector('textarea[data-sentence-id]');
        if (nextTextarea) {
            nextTextarea.focus();
            // Выделяем весь текст для удобства замены
            nextTextarea.select();
        }
        
        // Показываем уведомление о переходе
        showNotification(`Переход к предложению №${nextRow.querySelector('td:first-child a').textContent.trim()}`, 'info');
    } else {
        // Если это последнее предложение, показываем уведомление
        showNotification('Это последнее предложение в документе', 'info');
    }
}
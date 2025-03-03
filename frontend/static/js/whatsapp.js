import { showToast, showError } from './ui.js';
import { api } from './api.js';

// UI Elements
const whatsappSection = document.getElementById('whatsapp-section');
const searchSection = document.getElementById('search-section');
const whatsappNavBtn = document.getElementById('whatsapp-nav-btn');
const searchNavBtn = document.getElementById('search-nav-btn');
const accountForm = document.getElementById('account-form');
const addAccountBtn = document.getElementById('add-account-btn');
const accountsTable = document.getElementById('accounts-table');
const accountsBody = document.getElementById('accounts-body');
const accountsSearch = document.getElementById('accounts-search');
const sendMessageModal = document.getElementById('send-message-modal');
const sendMessageForm = document.getElementById('send-message-form');
const qrCodeModal = document.getElementById('qr-code-modal');
const qrCodeImage = document.getElementById('qr-code-image');
const qrStatusText = document.querySelector('.qr-status');
const messageHistoryModal = document.getElementById('message-history-modal');
const messageHistoryBody = document.getElementById('message-history-body');

// Constants
const QR_POLL_INTERVAL = 2000; // 2 seconds
const QR_POLL_MAX_TIME = 120000; // 2 minutes
const MESSAGE_STATUS_POLL_INTERVAL = 3000; // 3 seconds
const MESSAGE_STATUS_POLL_MAX_TIME = 300000; // 5 minutes

// State management
let qrCodeInterval = null;
let qrCodeTimeout = null;
let messageStatusPolls = new Map(); // Map of task_id -> {intervalId, timeoutId}
let currentAccountId = null;

// Navigation
whatsappNavBtn.addEventListener('click', () => {
    searchSection.classList.add('hidden');
    whatsappSection.classList.remove('hidden');
    whatsappNavBtn.classList.add('active');
    searchNavBtn.classList.remove('active');
    loadAccounts();
});

searchNavBtn.addEventListener('click', () => {
    whatsappSection.classList.add('hidden');
    searchSection.classList.remove('hidden');
    searchNavBtn.classList.add('active');
    whatsappNavBtn.classList.remove('active');
});

// Account Form
addAccountBtn.addEventListener('click', () => {
    accountForm.classList.toggle('hidden');
    
    // Если форма видима, фокусируемся на первом поле
    if (!accountForm.classList.contains('hidden')) {
        document.getElementById('profile-name').focus();
    }
});

accountForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const profileName = document.getElementById('profile-name').value;
    const description = document.getElementById('description').value;

    try {
        const submitBtn = accountForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating...';

        await api.post('/whatsapp/accounts', {
            profile_name: profileName,
            description: description
        });

        showToast('Account created successfully', 'success');
        accountForm.reset();
        accountForm.classList.add('hidden');
        await loadAccounts();
    } catch (error) {
        console.error('Failed to create account:', error);
        showToast(error.message || 'Failed to create account', 'error');
    } finally {
        const submitBtn = accountForm.querySelector('button[type="submit"]');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-save"></i> Save Account';
    }
});

// Accounts Table
async function loadAccounts() {
    try {
        const accounts = await api.get('/whatsapp/accounts');
        renderAccounts(accounts);
    } catch (error) {
        console.error('Failed to load accounts:', error);
        showToast('Failed to load accounts: ' + (error.message || 'Unknown error'), 'error');
    }
}

function renderAccounts(accounts) {
    accountsBody.innerHTML = '';
    
    if (accounts.length === 0) {
        // Показываем сообщение, если аккаунтов нет
        const emptyRow = document.createElement('tr');
        emptyRow.innerHTML = `
            <td colspan="5" class="text-center py-4">
                No WhatsApp accounts yet. Click "Add Account" to create one.
            </td>
        `;
        accountsBody.appendChild(emptyRow);
        return;
    }
    
    accounts.forEach(account => {
        const row = document.createElement('tr');
        const status = account.status?.toUpperCase() || 'PENDING';
        
        // Определение текста и класса для статуса
        let statusClass = 'status-' + status.toLowerCase();
        let statusIcon = '';
        
        switch (status) {
            case 'ACTIVE':
                statusIcon = 'fa-check-circle';
                break;
            case 'PENDING':
                statusIcon = 'fa-clock';
                break;
            case 'ERROR':
                statusIcon = 'fa-exclamation-circle';
                break;
            case 'BLOCKED':
                statusIcon = 'fa-ban';
                break;
            default:
                statusIcon = 'fa-circle';
        }
        
        // Форматирование времени последней активности
        let lastActive = account.last_active || '-';
        if (account.account_metadata && account.account_metadata.last_active) {
            try {
                const date = new Date(account.account_metadata.last_active);
                lastActive = date.toLocaleString();
            } catch (e) {
                lastActive = account.account_metadata.last_active;
            }
        }
        
        row.innerHTML = `
            <td>${account.profile_name}</td>
            <td>${account.description || '-'}</td>
            <td>
                <span class="status-badge status-${status.toLowerCase()}">
                    <i class="fas ${statusIcon}"></i>
                    ${status}
                </span>
            </td>
            <td>${lastActive}</td>
            <td class="whatsapp-actions">
                <button class="btn btn-init" onclick="initSession('${account.id}')" 
                        title="Initialize Session" ${status === 'ACTIVE' ? 'disabled' : ''}>
                    <i class="fas fa-qrcode"></i>
                </button>
                <button class="btn btn-send" onclick="showSendMessage('${account.id}')"
                        title="Send Message" ${status !== 'ACTIVE' ? 'disabled' : ''}>
                    <i class="fas fa-paper-plane"></i>
                </button>
                <button class="btn btn-history" onclick="showMessageHistory('${account.id}')"
                        title="Message History">
                    <i class="fas fa-history"></i>
                </button>
                <button class="btn btn-check" onclick="checkAccountStatus('${account.id}')"
                        title="Check Status">
                    <i class="fas fa-sync-alt"></i>
                </button>
                <button class="btn btn-delete" onclick="deleteAccount('${account.id}')"
                        title="Delete Account">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;
        accountsBody.appendChild(row);
    });
}

// Search Accounts
accountsSearch.addEventListener('input', (e) => {
    const searchTerm = e.target.value.toLowerCase();
    const rows = accountsBody.getElementsByTagName('tr');
    
    Array.from(rows).forEach(row => {
        // Пропускаем строку с сообщением о пустой таблице
        if (row.cells.length === 1) return;
        
        const profileName = row.cells[0].textContent.toLowerCase();
        const description = row.cells[1].textContent.toLowerCase();
        const visible = profileName.includes(searchTerm) || 
                       description.includes(searchTerm);
        row.style.display = visible ? '' : 'none';
    });
});

// QR Code handling
function clearQRPolling() {
    if (qrCodeInterval) {
        clearInterval(qrCodeInterval);
        qrCodeInterval = null;
    }
    
    if (qrCodeTimeout) {
        clearTimeout(qrCodeTimeout);
        qrCodeTimeout = null;
    }
}

// Исправление в файле frontend/static/js/whatsapp.js

// Изменение в функции pollQRCode
// Переменная для отслеживания последнего состояния QR-кода
let lastQrCodeState = null;

async function pollQRCode(accountId) {
    try {
        const response = await api.get(`/whatsapp/accounts/${accountId}/qr`);
        
        console.log('QR code poll response:', response.status, 'Authenticated:', response.authenticated, 'Close Modal:', response.close_modal);
        
        // Проверка на наличие флагов аутентификации и закрытия модального окна
        if (response.authenticated === true || response.close_modal === true || response.status === 'active') {
            console.log('Authentication detected, closing modal window and updating account list');
            
            // Показываем уведомление
            showToast('WhatsApp connected successfully', 'success');
            
            // Очищаем интервалы и закрываем модальное окно
            clearQRPolling();
            closeModal(qrCodeModal);
            
            // Обновляем список аккаунтов для отображения нового статуса
            await loadAccounts();
            
            return;
        }

        // Проверка на исчезновение QR-кода (был раньше, но сейчас нет)
        const qrDisappeared = lastQrCodeState && !response.qr_code;
        if (qrDisappeared) {
            console.log('QR code disappeared - likely scanned successfully');
            
            // Показываем уведомление
            showToast('QR код отсканирован, ожидание подтверждения', 'info');
            
            // Запускаем принудительную проверку статуса через 5 секунд
            setTimeout(() => {
                if (qrCodeModal.style.display === 'block') {
                    forceCheckStatus(accountId);
                }
            }, 5000);
        }

        // Сохраняем текущее состояние QR-кода для следующей проверки
        lastQrCodeState = response.qr_code;
        
        // Обновляем текст статуса
        if (qrStatusText) {
            qrStatusText.textContent = response.status_message || 'Waiting for QR code scan...';
            
            // Меняем цвет в зависимости от статуса
            if (response.status === 'active') {
                qrStatusText.style.color = '#28a745';  // Зеленый
            } else if (response.error) {
                qrStatusText.style.color = '#e74c3c';  // Красный
            } else {
                qrStatusText.style.color = '';         // По умолчанию
            }
        }

        // Управление индикатором загрузки и QR-кодом
        const loadingIndicator = document.querySelector('.loading-indicator');
        
        if (response.qr_code) {
            // Есть QR-код - показываем его
            qrCodeImage.src = `data:image/png;base64,${response.qr_code}`;
            qrCodeImage.style.display = 'block';
            
            // Скрываем индикатор загрузки
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
        } else if (response.status === 'active' || response.authenticated || qrDisappeared) {
            // Аккаунт активен - скрываем QR-код и показываем сообщение
            qrCodeImage.style.display = 'none';
            
            if (loadingIndicator) {
                loadingIndicator.style.display = 'block';
                loadingIndicator.innerHTML = '<i class="fas fa-check-circle"></i> WhatsApp connected successfully!';
            }
            
            // Добавим здесь: если QR-код исчез (был, но больше нет), считаем что сессия активирована
            clearQRPolling();
            
            // Немного подождем и перезагрузим список аккаунтов
            setTimeout(async () => {
                closeModal(qrCodeModal);
                await loadAccounts();
            }, 2000);
        } else {
            // Инициализация или другое состояние - показываем индикатор загрузки
            if (!qrCodeImage.src || qrCodeImage.src.includes('placeholder')) {
                qrCodeImage.style.display = 'none';
                
                if (loadingIndicator) {
                    loadingIndicator.style.display = 'block';
                    loadingIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Initializing WhatsApp...';
                }
            }
        }

        // Обработка ошибок
        if (response.error) {
            if (qrStatusText) {
                qrStatusText.textContent = response.error;
                qrStatusText.style.color = '#e74c3c';  // Красный
            }
        }

    } catch (error) {
        console.error('Error polling QR code:', error);
        
        if (qrStatusText) {
            qrStatusText.textContent = 'Error: ' + (error.message || 'Failed to check QR code');
            qrStatusText.style.color = '#e74c3c';  // Красный
        }
    }
}

// Добавим в window новую функцию для принудительной проверки статуса
window.forceCheckStatus = async (accountId) => {
    try {
        // Показываем уведомление
        showToast('Checking WhatsApp connection status...', 'info');
        
        // Запрашиваем проверку статуса
        const response = await api.post(`/whatsapp/accounts/${accountId}/check`);
        
        if (response.task_id) {
            showToast('Status check initiated', 'info');
            
            // Опрашиваем статус задачи
            const checkInterval = setInterval(async () => {
                try {
                    const taskStatus = await api.get(`/whatsapp/tasks/${response.task_id}`);
                    if (taskStatus.done) {
                        clearInterval(checkInterval);
                        
                        if (taskStatus.result?.status === 'active') {
                            // Если аккаунт активен, закрываем модальное окно и обновляем список
                            showToast('WhatsApp connected successfully', 'success');
                            clearQRPolling();
                            closeModal(qrCodeModal);
                            await loadAccounts();
                        } else {
                            showToast(`Status: ${taskStatus.result?.status || 'unknown'}`, 'info');
                        }
                    }
                } catch (error) {
                    console.error('Error checking task status:', error);
                }
            }, 2000);
            
            // Ограничиваем время опроса
            setTimeout(() => {
                clearInterval(checkInterval);
            }, 30000);
        }
    } catch (error) {
        console.error('Error checking status:', error);
        showToast('Failed to check status: ' + (error.message || 'Unknown error'), 'error');
    }
};

// Initialize Session
window.initSession = async (accountId) => {
    try {
        clearQRPolling();
        
        // Показываем модальное окно с начальным состоянием
        openModal(qrCodeModal);
        
        // Настраиваем UI
        qrCodeImage.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2YwZjBmMCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIiBmaWxsPSIjNjY2Ij5Preparing QR code...</text></svg>';
        qrCodeImage.style.display = 'block';
        
        if (qrStatusText) {
            qrStatusText.textContent = 'Status: Initializing...';
            qrStatusText.style.color = '';
        }

        // Создаем индикатор загрузки, если его нет
        let loadingIndicator = document.querySelector('.loading-indicator');
        if (!loadingIndicator) {
            loadingIndicator = document.createElement('div');
            loadingIndicator.className = 'loading-indicator';
            loadingIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preparing WhatsApp...';
            qrCodeImage.parentNode.insertBefore(loadingIndicator, qrCodeImage.nextSibling);
        } else {
            loadingIndicator.style.display = 'block';
        }

        // Инициализируем сессию
        const response = await api.post(`/whatsapp/accounts/${accountId}/init`, {
            wait_time: 120
        });

        if (response.error) {
            clearQRPolling();
            showToast('Session initialization failed: ' + response.error, 'error');
            
            if (qrStatusText) {
                qrStatusText.textContent = 'Error: ' + response.error;
                qrStatusText.style.color = '#e74c3c';
            }
            
            // Не закрываем модальное окно, чтобы пользователь мог прочитать ошибку
            return;
        }

        // Начинаем опрос QR-кода
        startQRPolling(accountId);

    } catch (error) {
        console.error('Session initialization error:', error);
        clearQRPolling();
        
        showToast('Session initialization failed: ' + (error.message || 'Unknown error'), 'error');
        
        if (qrStatusText) {
            qrStatusText.textContent = 'Error: ' + (error.message || 'Failed to initialize session');
            qrStatusText.style.color = '#e74c3c';
        }
    }
};

function startQRPolling(accountId) {
    clearQRPolling();
    currentAccountId = accountId;
    
    // Начинаем опрос
    qrCodeInterval = setInterval(() => pollQRCode(accountId), QR_POLL_INTERVAL);
    
    // Устанавливаем таймаут
    qrCodeTimeout = setTimeout(() => {
        clearQRPolling();
        if (qrStatusText) {
            qrStatusText.textContent = 'QR code timed out. Please try again.';
            qrStatusText.style.color = '#e74c3c';
        }
    }, QR_POLL_MAX_TIME);
    
    // Запускаем первую проверку немедленно
    pollQRCode(accountId);
}

// Check Account Status
window.checkAccountStatus = async (accountId) => {
    try {
        const statusBtn = document.querySelector(`.btn-check[onclick="checkAccountStatus('${accountId}')"]`);
        if (statusBtn) {
            const originalHTML = statusBtn.innerHTML;
            statusBtn.disabled = true;
            statusBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            
            try {
                // Запускаем задачу проверки статуса
                const response = await api.post(`/whatsapp/accounts/${accountId}/check`);
                
                if (response.task_id) {
                    showToast('Status check scheduled', 'info');
                    
                    // Периодически проверяем статус задачи
                    const taskCheckInterval = setInterval(async () => {
                        try {
                            const taskStatus = await api.get(`/whatsapp/tasks/${response.task_id}`);
                            
                            if (taskStatus.done) {
                                clearInterval(taskCheckInterval);
                                
                                if (taskStatus.result && taskStatus.result.status) {
                                    showToast(`Account status: ${taskStatus.result.status}`, 'info');
                                    
                                    // Обновляем список аккаунтов
                                    await loadAccounts();
                                } else if (taskStatus.error) {
                                    showToast(`Status check error: ${taskStatus.error}`, 'error');
                                }
                            }
                        } catch (error) {
                            console.error('Error checking task status:', error);
                        }
                    }, 2000);
                    
                    // Очищаем интервал через 30 секунд
                    setTimeout(() => {
                        clearInterval(taskCheckInterval);
                    }, 30000);
                }
                
            } finally {
                statusBtn.disabled = false;
                statusBtn.innerHTML = originalHTML;
            }
        }
    } catch (error) {
        console.error('Status check error:', error);
        showToast('Failed to check status: ' + (error.message || 'Unknown error'), 'error');
    }
};

// Send Message
window.showSendMessage = (accountId) => {
    sendMessageForm.reset();
    sendMessageForm.dataset.accountId = accountId;
    
    openModal(sendMessageModal);
    
    // Сбрасываем режим на одиночный
    const singleBtn = document.querySelector('.mode-btn[data-mode="single"]');
    const bulkBtn = document.querySelector('.mode-btn[data-mode="bulk"]');
    const singleRecipient = document.getElementById('single-recipient');
    const bulkRecipients = document.getElementById('bulk-recipients');
    
    singleBtn.classList.add('active');
    bulkBtn.classList.remove('active');
    singleRecipient.classList.remove('hidden');
    bulkRecipients.classList.add('hidden');
    
    // Фокусируемся на первом поле
    document.getElementById('recipient-phone').focus();
};

// Message Mode Toggle
document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const singleRecipient = document.getElementById('single-recipient');
        const bulkRecipients = document.getElementById('bulk-recipients');
        
        // Обновляем состояние кнопок
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Показываем/скрываем соответствующие поля
        if (mode === 'single') {
            singleRecipient.classList.remove('hidden');
            bulkRecipients.classList.add('hidden');
            document.getElementById('recipient-phone').focus();
        } else {
            singleRecipient.classList.add('hidden');
            bulkRecipients.classList.remove('hidden');
            document.getElementById('bulk-phones').focus();
        }
    });
});

// Message History
window.showMessageHistory = async (accountId) => {
    try {
        openModal(messageHistoryModal);
        
        // Показываем индикатор загрузки
        messageHistoryBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4">
                    <i class="fas fa-spinner fa-spin mr-2"></i> Loading message history...
                </td>
            </tr>
        `;
        
        currentAccountId = accountId;
        const messages = await api.get(`/whatsapp/accounts/${accountId}/messages`);
        renderMessageHistory(messages);
    } catch (error) {
        console.error('Failed to load message history:', error);
        
        // Показываем ошибку
        messageHistoryBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-circle mr-2"></i> Error loading messages: ${error.message || 'Unknown error'}
                </td>
            </tr>
        `;
    }
};

function renderMessageHistory(messages) {
    messageHistoryBody.innerHTML = '';
    
    if (!messages || messages.length === 0) {
        messageHistoryBody.innerHTML = `
            <tr>
                <td colspan="5" class="text-center py-4">
                    No messages found.
                </td>
            </tr>
        `;
        return;
    }
    
    messages.forEach(message => {
        const row = document.createElement('tr');
        const status = message.status?.toUpperCase() || 'PENDING';
        
        try {
            // Форматируем дату
            const timestamp = new Date(message.created_at).toLocaleString();
            
            // Определяем классы для статуса
            let statusClass = '';
            switch (status) {
                case 'SENT':
                    statusClass = 'status-active';
                    break;
                case 'PENDING':
                    statusClass = 'status-pending';
                    break;
                case 'ERROR':
                    statusClass = 'status-error';
                    break;
                default:
                    statusClass = '';
            }
            
            // Форматируем текст сообщения (ограничиваем длину)
            const messageText = message.message_text ? 
                (message.message_text.length > 50 ? 
                    message.message_text.substring(0, 50) + '...' : 
                    message.message_text) : 
                'No message text';
            
            row.innerHTML = `
                <td>${message.recipient}</td>
                <td title="${message.message_text || ''}">${messageText}</td>
                <td>
                    <span class="status-badge ${statusClass}">
                        ${status}
                    </span>
                </td>
                <td>${timestamp}</td>
                <td>${message.error_message || '-'}</td>
            `;
            messageHistoryBody.appendChild(row);
            
        } catch (e) {
            console.error('Error rendering message row:', e);
        }
    });
}

// Message Status Polling
function startMessageStatusPolling(taskId) {
    if (messageStatusPolls.has(taskId)) return;
    
    const intervalId = setInterval(async () => {
        try {
            const status = await api.get(`/whatsapp/tasks/${taskId}`);
            if (status.done) {
                clearInterval(messageStatusPolls.get(taskId).intervalId);
                clearTimeout(messageStatusPolls.get(taskId).timeoutId);
                messageStatusPolls.delete(taskId);
                
                if (status.result?.success) {
                    showToast('Message sent successfully', 'success');
                } else {
                    console.error('Message sending failed:', status.error || 'Unknown error');
                    showToast('Message sending failed: ' + (status.error || 'Unknown error'), 'error');
                }
                
                // Обновляем историю сообщений, если модальное окно открыто
                if (messageHistoryModal.style.display === 'block' && currentAccountId) {
                    await showMessageHistory(currentAccountId);
                }
            }
        } catch (error) {
            console.error('Error polling message status:', error);
        }
    }, MESSAGE_STATUS_POLL_INTERVAL);
    
    // Устанавливаем таймаут на случай, если статус не изменится
    const timeoutId = setTimeout(() => {
        clearInterval(intervalId);
        messageStatusPolls.delete(taskId);
        console.error('Message status polling timed out');
    }, MESSAGE_STATUS_POLL_MAX_TIME);
    
    messageStatusPolls.set(taskId, { intervalId, timeoutId });
}

// Parse bulk phone numbers
function parseBulkPhoneNumbers(text) {
    return text.split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0)
        .map(phone => ({
            phone: phone,
            message: document.getElementById('message-text').value
        }));
}

// Handle message form submission
sendMessageForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const accountId = sendMessageForm.dataset.accountId;
    const message = document.getElementById('message-text').value;
    const mode = document.querySelector('.mode-btn.active').dataset.mode;
    
    if (!message.trim()) {
        showToast('Please enter a message', 'error');
        return;
    }

    try {
        // Получаем получателей
        let recipients;
        if (mode === 'single') {
            const phone = document.getElementById('recipient-phone').value;
            if (!phone.trim()) {
                showToast('Please enter a phone number', 'error');
                return;
            }
            recipients = [{ phone, message }];
        } else {
            const bulkPhones = document.getElementById('bulk-phones').value;
            if (!bulkPhones.trim()) {
                showToast('Please enter phone numbers', 'error');
                return;
            }
            recipients = parseBulkPhoneNumbers(bulkPhones);
            if (recipients.length === 0) {
                showToast('No valid phone numbers found', 'error');
                return;
            }
        }

        // Блокируем кнопку отправки
        const submitBtn = sendMessageForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';

        try {
            // Отправляем сообщение
            const response = await api.post(`/whatsapp/accounts/${accountId}/send`, {
                account_id: accountId,
                recipients: recipients,
                wait_time: 60
            });

            if (response?.task_id) {
                const recipientCount = recipients.length;
                showToast(
                    `${recipientCount} message${recipientCount > 1 ? 's' : ''} queued for sending`,
                    'info'
                );
                closeModal(sendMessageModal);
                currentAccountId = accountId;
                startMessageStatusPolling(response.task_id);
            } else {
                throw new Error('Invalid response from server');
            }
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    } catch (error) {
        console.error('Failed to send message:', error);
        showToast('Failed to send message: ' + (error.message || 'Unknown error'), 'error');
    }
});

// Modal handling
function openModal(modal) {
    document.body.style.overflow = 'hidden';
    modal.style.display = 'block';
    modal.classList.remove('hidden');
    
    // Включаем анимацию появления
    setTimeout(() => {
        modal.classList.add('fade-in');
    }, 10);
}

function closeModal(modal) {
    // Очищаем любые интервалы и таймауты
    if (modal === qrCodeModal) {
        clearQRPolling();
        qrCodeImage.src = '';
        
        // Сбрасываем статус
        if (qrStatusText) {
            qrStatusText.textContent = '';
        }
        
        // Скрываем индикатор загрузки
        const loadingIndicator = document.querySelector('.loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.style.display = 'none';
        }
        
        // Проверяем, нужно ли обновлять список аккаунтов после закрытия
        const currentAccountElem = modal.querySelector('[data-account-id]');
        const accountId = currentAccountElem ? currentAccountElem.getAttribute('data-account-id') : null;
        
        if (accountId) {
            // Асинхронно обновляем список аккаунтов для актуализации статусов
            setTimeout(async () => {
                try {
                    await loadAccounts();
                } catch (error) {
                    console.error('Error updating accounts after modal close:', error);
                }
            }, 500);
        }
    } else if (modal === sendMessageModal) {
        sendMessageForm.reset();
    } else if (modal === messageHistoryModal) {
        currentAccountId = null;
    }
    
    // Включаем анимацию исчезновения
    modal.classList.remove('fade-in');
    
    // Задержка перед скрытием для анимации
    setTimeout(() => {
        document.body.style.overflow = '';
        modal.style.display = 'none';
        modal.classList.add('hidden');
    }, 300);
}

// Modal Close Buttons
document.querySelectorAll('.cancel-btn, .close').forEach(btn => {
    btn.addEventListener('click', () => {
        const modal = btn.closest('.modal');
        closeModal(modal);
    });
});

// Close modal on outside click
window.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        closeModal(e.target);
    }
});

// Delete Account
window.deleteAccount = async (accountId) => {
    // Запрашиваем подтверждение
    if (!confirm('Are you sure you want to delete this account? This action cannot be undone.')) {
        return;
    }

    try {
        // Находим кнопку удаления
        const deleteBtn = document.querySelector(`.btn-delete[onclick="deleteAccount('${accountId}')"]`);
        if (deleteBtn) {
            const originalHTML = deleteBtn.innerHTML;
            deleteBtn.disabled = true;
            deleteBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            
            try {
                await api.deleteWhatsAppAccount(accountId);
                showToast('Account successfully deleted', 'success');
                await loadAccounts();
            } finally {
                deleteBtn.disabled = false;
                deleteBtn.innerHTML = originalHTML;
            }
        } else {
            await api.deleteWhatsAppAccount(accountId);
            showToast('Account successfully deleted', 'success');
            await loadAccounts();
        }
    } catch (error) {
        console.error('Failed to delete account:', error);
        showToast('Failed to delete account: ' + (error.message || 'Unknown error'), 'error');
    }
};

// Logout Account
window.logoutAccount = async (accountId) => {
    if (!confirm('Are you sure you want to log out from this WhatsApp account?')) {
        return;
    }

    try {
        const response = await api.post(`/whatsapp/accounts/${accountId}/logout`);
        
        if (response.task_id) {
            showToast('Logout scheduled', 'info');
            
            // Ждем завершения задачи
            const checkInterval = setInterval(async () => {
                try {
                    const status = await api.get(`/whatsapp/tasks/${response.task_id}`);
                    if (status.done) {
                        clearInterval(checkInterval);
                        
                        if (status.result?.success) {
                            showToast('Successfully logged out from WhatsApp', 'success');
                        } else {
                            showToast('Logout failed: ' + (status.error || 'Unknown error'), 'error');
                        }
                        
                        // Обновляем список аккаунтов
                        await loadAccounts();
                    }
                } catch (error) {
                    console.error('Error checking logout status:', error);
                }
            }, 2000);
            
            // Очищаем интервал через 30 секунд
            setTimeout(() => {
                clearInterval(checkInterval);
            }, 30000);
        }
    } catch (error) {
        console.error('Failed to logout account:', error);
        showToast('Failed to logout: ' + (error.message || 'Unknown error'), 'error');
    }
};

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    clearQRPolling();
    
    // Очищаем все интервалы и таймауты для отслеживания статуса сообщений
    messageStatusPolls.forEach((poll) => {
        clearInterval(poll.intervalId);
        clearTimeout(poll.timeoutId);
    });
    messageStatusPolls.clear();
});

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (!whatsappSection.classList.contains('hidden')) {
        loadAccounts();
    }
    
    // Добавляем класс для анимации модальных окон
    document.querySelectorAll('.modal-content').forEach(content => {
        content.classList.add('animate');
    });
});

// Добавляем эффекты перехода для кнопок
document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-2px)';
    });
    
    btn.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
    });
});

// Экспортируем функции для доступа из других модулей
export { loadAccounts };
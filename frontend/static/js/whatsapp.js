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
const messageHistoryModal = document.getElementById('message-history-modal');
const messageHistoryBody = document.getElementById('message-history-body');

// Constants
const QR_POLL_INTERVAL = 2000; // 2 seconds
const MODAL_TIMEOUT = 120000; // 120 seconds
const MAX_RETRIES = 3;
const MESSAGE_STATUS_POLL_INTERVAL = 3000; // 3 seconds

// State management
let qrCodeInterval = null;
let modalTimeout = null;
let hasShownQRCode = false;
let retryCount = 0;
let currentAccountId = null;
let isProcessingStatus = false;
let messageStatusPolls = new Map(); // Map of task_id -> interval ID

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
});

accountForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const profileName = document.getElementById('profile-name').value;
    const description = document.getElementById('description').value;

    try {
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
    }
});

// Accounts Table
async function loadAccounts() {
    try {
        const accounts = await api.get('/whatsapp/accounts');
        renderAccounts(accounts);
    } catch (error) {
        console.error('Failed to load accounts:', error);
    }
}

function renderAccounts(accounts) {
    accountsBody.innerHTML = '';
    accounts.forEach(account => {
        const row = document.createElement('tr');
        const status = account.status?.toUpperCase() || 'PENDING';
        row.innerHTML = `
            <td>${account.profile_name}</td>
            <td>${account.description || '-'}</td>
            <td>
                <span class="status-badge status-${status.toLowerCase()}">
                    <i class="fas fa-circle"></i>
                    ${status}
                </span>
            </td>
            <td>${account.last_active || '-'}</td>
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
        const profileName = row.cells[0].textContent.toLowerCase();
        const description = row.cells[1].textContent.toLowerCase();
        const visible = profileName.includes(searchTerm) || 
                       description.includes(searchTerm);
        row.style.display = visible ? '' : 'none';
    });
});

// Status checking and QR code handling
async function checkAccountStatus(accountId) {
    if (isProcessingStatus) return;
    
    try {
        isProcessingStatus = true;
        const accountResponse = await api.get(`/whatsapp/accounts/${accountId}`);
        const status = accountResponse?.status?.toUpperCase();

        if (status === 'ACTIVE') {
            clearPolling();
            showToast('WhatsApp connected successfully', 'success');
            closeModal(qrCodeModal);
            await loadAccounts();
            return true;
        }
        
        if (status === 'ERROR' || status === 'DISCONNECTED') {
            throw new Error(accountResponse.error || 'Connection failed');
        }

        return false;
    } catch (error) {
        console.error('Status check error:', error);
        return false;
    } finally {
        isProcessingStatus = false;
    }
}

async function checkQRCode(accountId) {
    try {
        // First check if already connected
        const isConnected = await checkAccountStatus(accountId);
        if (isConnected) return;

        const response = await api.get(`/whatsapp/accounts/${accountId}/qr`);
        const statusText = document.querySelector('.qr-status');
        const loadingIndicator = document.querySelector('.loading-indicator');

        // Update status message
        if (statusText) {
            statusText.textContent = response.status_message || 'Waiting for QR code scan...';
        }

        // Handle QR code display
        if (response.qr_code) {
            qrCodeImage.src = `data:image/png;base64,${response.qr_code}`;
            qrCodeImage.style.display = 'block';
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            // Reset timeout when QR code is received
            if (modalTimeout) {
                clearTimeout(modalTimeout);
                modalTimeout = null;
            }
        } else {
            if (loadingIndicator) {
                loadingIndicator.style.display = 'block';
            }
            qrCodeImage.style.display = 'none';
        }

        // Handle errors
        if (response.error) {
            retryCount++;
            if (retryCount >= MAX_RETRIES) {
                throw new Error(response.error);
            }
        } else {
            retryCount = 0;
        }

    } catch (error) {
        console.error('QR code check error:', error);
        clearPolling();
        closeModal(qrCodeModal);
    }
}

function startQRCodePolling(accountId) {
    clearPolling();
    currentAccountId = accountId;
    // Add initial delay before first request
    setTimeout(async () => {
        await checkQRCode(accountId);
        // Start regular polling after first request
        qrCodeInterval = setInterval(() => checkQRCode(accountId), QR_POLL_INTERVAL);
    }, 3000); // Give 3 seconds for browser initialization
}

function clearPolling() {
    if (qrCodeInterval) {
        clearInterval(qrCodeInterval);
        qrCodeInterval = null;
    }
    if (modalTimeout) {
        clearTimeout(modalTimeout);
        modalTimeout = null;
    }
    currentAccountId = null;
    retryCount = 0;
}

// Initialize Session
window.initSession = async (accountId) => {
    try {
        clearPolling();
        
        // Show modal with initial state
        qrCodeModal.classList.remove('hidden');
        qrCodeModal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        
        // Setup UI
        qrCodeImage.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2YwZjBmMCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIiBmaWxsPSIjNjY2Ij5Preparing QR code...</text></svg>';
        qrCodeImage.style.display = 'block';
        
        const statusText = document.querySelector('.qr-status');
        if (statusText) {
            statusText.textContent = 'Status: Initializing...';
        }

        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'loading-indicator';
        loadingIndicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preparing WhatsApp...';
        qrCodeImage.parentNode.insertBefore(loadingIndicator, qrCodeImage.nextSibling);

        // Start polling immediately
        startQRCodePolling(accountId);
        
        // Set timeout
        modalTimeout = setTimeout(() => {
            clearPolling();
            console.error('QR code generation timeout');
            closeModal(qrCodeModal);
        }, MODAL_TIMEOUT);

        // Initialize session
        const response = await api.post(`/whatsapp/accounts/${accountId}/init`, {
            wait_time: 120
        });

        if (response.error) {
            clearPolling();
            console.error('Session initialization failed:', response.error);
            closeModal(qrCodeModal);
            return;
        }

        // If QR code came in initialization response, show it
        if (response.qr_code) {
            qrCodeImage.src = `data:image/png;base64,${response.qr_code}`;
            qrCodeImage.style.display = 'block';
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
        }

    } catch (error) {
        console.error('Session initialization error:', error);
        clearPolling();
        closeModal(qrCodeModal);
    }
};

// Send Message
window.showSendMessage = (accountId) => {
    sendMessageForm.reset();
    sendMessageForm.dataset.accountId = accountId;
    
    document.body.style.overflow = 'hidden';
    sendMessageModal.style.display = 'block';
    sendMessageModal.classList.remove('hidden');
    
    // Reset mode to single
    const singleBtn = document.querySelector('.mode-btn[data-mode="single"]');
    const bulkBtn = document.querySelector('.mode-btn[data-mode="bulk"]');
    const singleRecipient = document.getElementById('single-recipient');
    const bulkRecipients = document.getElementById('bulk-recipients');
    
    singleBtn.classList.add('active');
    bulkBtn.classList.remove('active');
    singleRecipient.classList.remove('hidden');
    bulkRecipients.classList.add('hidden');
    
    document.getElementById('recipient-phone').focus();
};

// Message Mode Toggle
document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        const singleRecipient = document.getElementById('single-recipient');
        const bulkRecipients = document.getElementById('bulk-recipients');
        
        // Update button states
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Show/hide appropriate input
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
        currentAccountId = accountId; // Store current account ID
        const messages = await api.get(`/whatsapp/accounts/${accountId}/messages`);
        renderMessageHistory(messages);
        messageHistoryModal.classList.remove('hidden');
        messageHistoryModal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    } catch (error) {
        console.error('Failed to load message history:', error);
    }
};

function renderMessageHistory(messages) {
    messageHistoryBody.innerHTML = '';
    messages.forEach(message => {
        const row = document.createElement('tr');
        const status = message.status?.toUpperCase() || 'PENDING';
        const timestamp = new Date(message.created_at).toLocaleString();
        row.innerHTML = `
            <td>${message.recipient}</td>
            <td>${message.message_text}</td>
            <td>
                <span class="status-badge status-${status.toLowerCase()}">
                    ${status}
                </span>
            </td>
            <td>${timestamp}</td>
            <td>${message.error_message || '-'}</td>
        `;
        messageHistoryBody.appendChild(row);
    });
}

// Message Status Polling
function startMessageStatusPolling(taskId) {
    if (messageStatusPolls.has(taskId)) return;
    
    const intervalId = setInterval(async () => {
        try {
            const status = await api.get(`/whatsapp/tasks/${taskId}`);
            if (status.done) {
                clearInterval(messageStatusPolls.get(taskId));
                messageStatusPolls.delete(taskId);
                
                if (status.result?.success) {
                    showToast('Message sent successfully', 'success');
                } else {
                    console.error('Message sending failed:', status.error || 'Unknown error');
                }
                
                // Refresh message history if modal is open
                if (!messageHistoryModal.classList.contains('hidden') && currentAccountId) {
                    await showMessageHistory(currentAccountId);
                }
            }
        } catch (error) {
            console.error('Error polling message status:', error);
        }
    }, MESSAGE_STATUS_POLL_INTERVAL);
    
    messageStatusPolls.set(taskId, intervalId);
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
    } catch (error) {
        console.error('Failed to send message:', error);
        showToast('Failed to send message: ' + error.message, 'error');
    }
});

// Modal handling
function closeModal(modal) {
    if (modal === qrCodeModal) {
        clearPolling();
        qrCodeImage.src = '';
        qrCodeImage.style.display = 'none';
        
        const statusText = document.querySelector('.qr-status');
        if (statusText) {
            statusText.textContent = '';
        }
        
        const loadingIndicator = document.querySelector('.loading-indicator');
        if (loadingIndicator) {
            loadingIndicator.remove();
        }
    } else if (modal === sendMessageModal) {
        sendMessageForm.reset();
    } else if (modal === messageHistoryModal) {
        currentAccountId = null; // Clear current account ID when closing history
    }
    
    document.body.style.overflow = '';
    modal.style.display = 'none';
    modal.classList.add('hidden');
}

// Modal Close Buttons
document.querySelectorAll('.cancel-btn').forEach(btn => {
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

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    clearPolling();
    // Clear all message status polling intervals
    messageStatusPolls.forEach((intervalId) => clearInterval(intervalId));
    messageStatusPolls.clear();
});

// Delete Account
window.deleteAccount = async (accountId) => {
    if (!confirm('Are you sure you want to delete this account? This action cannot be undone.')) {
        return;
    }

    try {
        await api.deleteWhatsAppAccount(accountId);
        showToast('Account successfully deleted', 'success');
        await loadAccounts();
    } catch (error) {
        console.error('Failed to delete account:', error);
    }
};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (!whatsappSection.classList.contains('hidden')) {
        loadAccounts();
    }
});
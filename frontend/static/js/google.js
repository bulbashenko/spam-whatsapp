// Google Contacts Integration
import { api } from './api.js';
import { showToast } from './ui.js';

class GoogleContactsManager {
    constructor() {
        this.isConnected = false;
        this.accountInfo = null;
        this.initialize();
        this.setupEventListeners();
    }

    async initialize() {
        // Only check if logged in
        if (localStorage.getItem('token')) {
            await this.checkConnectionStatus();
            this.updateUI();
        }
    }

    setupEventListeners() {
        try {
            // Navigation
            const googleNavBtn = document.getElementById('google-nav-btn');
            if (googleNavBtn) {
                googleNavBtn.addEventListener('click', () => {
                    this.showGoogleSection();
                });
            }

            // Connect buttons - with null checks
            const connectGoogleBtn = document.getElementById('connect-google-btn');
            if (connectGoogleBtn) {
                connectGoogleBtn.addEventListener('click', () => {
                    this.connectGoogleAccount();
                });
            }
            
            const connectGoogleAccountBtn = document.getElementById('connect-google-account-btn');
            if (connectGoogleAccountBtn) {
                connectGoogleAccountBtn.addEventListener('click', () => {
                    this.connectGoogleAccount();
                });
            }

            // Disconnect buttons - with null checks
            const disconnectGoogleBtn = document.getElementById('disconnect-google-btn');
            if (disconnectGoogleBtn) {
                disconnectGoogleBtn.addEventListener('click', () => {
                    this.disconnectGoogleAccount();
                });
            }
            
            const disconnectGoogleAccountBtn = document.getElementById('disconnect-google-account-btn');
            if (disconnectGoogleAccountBtn) {
                disconnectGoogleAccountBtn.addEventListener('click', () => {
                    this.disconnectGoogleAccount();
                });
            }

            // Global event listeners
            document.addEventListener('user-logged-in', () => {
                this.checkConnectionStatus();
            });

            document.addEventListener('user-logged-out', () => {
                this.isConnected = false;
                this.accountInfo = null;
                this.updateUI();
            });
        } catch (error) {
            console.warn('Error setting up Google event listeners:', error);
        }
    }

    showGoogleSection() {
        // Hide all sections
        document.querySelectorAll('.container').forEach(container => {
            container.classList.add('hidden');
        });

        // Show Google section
        document.getElementById('google-section').classList.remove('hidden');

        // Update active navigation
        document.querySelectorAll('.nav-links .btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById('google-nav-btn').classList.add('active');

        // Update UI
        this.updateUI();
    }

    async checkConnectionStatus() {
        try {
            const statusData = await api.getGoogleConnectionStatus();
            this.isConnected = statusData.connected;
            this.accountInfo = statusData;
        } catch (error) {
            console.error('Error checking Google connection status:', error);
            this.isConnected = false;
            this.accountInfo = null;
        }
        this.updateUI();
    }

    async connectGoogleAccount() {
        try {
            const response = await api.getGoogleAuthUrl();
            
            if (response && response.auth_url) {
                // Check if there's a development mode note
                if (response.dev_mode_note) {
                    console.info(response.dev_mode_note);
                    showToast(response.dev_mode_note, 'warning', 8000);  // Show for longer (8 seconds)
                }
                
                // Open the Google authorization URL in a new window
                window.open(response.auth_url, 'GoogleAuth', 
                    'width=600,height=600,scrollbars=yes');
                
                showToast('Google authentication window opened. Please complete the authorization process.', 'info');
                
                // Set up polling to check connection status after redirection
                this.startStatusPolling();
            } else {
                showToast('Failed to get Google authorization URL', 'error');
            }
        } catch (error) {
            console.error('Error getting Google auth URL:', error);
            
            // Handle specific Google errors
            if (error.message && error.message.includes('OAuth client ID not configured')) {
                showToast('Error: Google OAuth configuration issue. Please contact the administrator.', 'error');
            } else if (error.message && error.message.includes('access_denied')) {
                showToast('Error: Google access denied. This app may require you to be added as a test user in Google Cloud Console.', 'error');
            } else if (error.message && error.message.includes('insufficient authentication scopes') || 
                       error.message && error.message.includes('ACCESS_TOKEN_SCOPE_INSUFFICIENT')) {
                // Show a special toast for insufficient scopes that prompts reconnection
                showToast('Your Google connection needs additional permissions. Please disconnect and reconnect your account.', 'warning', 8000);
                
                // Automatically show disconnect button
                const disconnectBtn = document.getElementById('disconnect-google-btn');
                if (disconnectBtn) {
                    disconnectBtn.classList.remove('hidden');
                }
                
                // Update UI state to show reconnection is needed
                const statusText = document.getElementById('google-status-text');
                if (statusText) {
                    statusText.textContent = 'Google account requires reconnection';
                    statusText.classList.add('text-warning');
                }
            } else {
                showToast('Error connecting to Google: ' + error.message, 'error');
            }
        }
    }

    startStatusPolling() {
        let attempts = 0;
        const maxAttempts = 10;
        const interval = 3000; // 3 seconds
        
        const poll = async () => {
            if (attempts >= maxAttempts) {
                showToast('Google authorization timed out. Please try again.', 'error');
                return;
            }
            
            try {
                await this.checkConnectionStatus();
                
                if (this.isConnected) {
                    showToast('Successfully connected to Google Contacts!', 'success');
                } else {
                    attempts++;
                    setTimeout(poll, interval);
                }
            } catch (error) {
                attempts++;
                setTimeout(poll, interval);
            }
        };
        
        setTimeout(poll, 5000); // Start polling after 5 seconds
    }

    async disconnectGoogleAccount() {
        try {
            await api.disconnectGoogleAccount();
            this.isConnected = false;
            this.accountInfo = null;
            
            showToast('Successfully disconnected from Google Contacts', 'success');
            this.updateUI();
        } catch (error) {
            console.error('Error disconnecting Google account:', error);
            showToast('Error disconnecting from Google: ' + error.message, 'error');
        }
    }

    updateUI() {
        try {
            const statusBar = document.getElementById('google-status-bar');
            const statusText = document.getElementById('google-status-text');
            const connectBtn = document.getElementById('connect-google-btn');
            const disconnectBtn = document.getElementById('disconnect-google-btn');
            
            // Google section elements
            const notConnectedSection = document.getElementById('google-not-connected');
            const connectedSection = document.getElementById('google-connected');
            const googleEmail = document.getElementById('google-email');
            const connectedDate = document.getElementById('google-connected-date');
            
            // If any required elements are missing, exit gracefully
            if (!statusBar || !statusText) {
                console.warn('Google UI elements not found, skipping UI update');
                return;
            }
            
            if (!localStorage.getItem('token')) {
                // User not logged in, hide everything
                if (statusBar) statusBar.classList.add('hidden');
                return;
            }
            
            // Show status bar
            if (statusBar) statusBar.classList.remove('hidden');
            
            if (this.isConnected) {
                // Connected state
                if (statusText) statusText.textContent = 'Connected to Google Contacts';
                if (connectBtn) connectBtn.classList.add('hidden');
                if (disconnectBtn) disconnectBtn.classList.remove('hidden');
                
                // Update Google section
                if (notConnectedSection) notConnectedSection.classList.add('hidden');
                if (connectedSection) connectedSection.classList.remove('hidden');
                
                // Update connected account info
                if (this.accountInfo) {
                    if (googleEmail) googleEmail.textContent = this.accountInfo.email || 'Unknown';
                    
                    // Format connected date
                    if (connectedDate && this.accountInfo.connected_at) {
                        const date = new Date(this.accountInfo.connected_at);
                        connectedDate.textContent = date.toLocaleDateString();
                    } else if (connectedDate) {
                        connectedDate.textContent = 'Unknown';
                    }
                }
            } else {
                // Not connected state
                if (statusText) statusText.textContent = 'Google Contacts not connected';
                if (connectBtn) connectBtn.classList.remove('hidden');
                if (disconnectBtn) disconnectBtn.classList.add('hidden');
                
                // Update Google section
                if (notConnectedSection) notConnectedSection.classList.remove('hidden');
                if (connectedSection) connectedSection.classList.add('hidden');
            }
        } catch (error) {
            console.warn('Error updating Google UI:', error);
        }
    }
}

// Initialize the Google Contacts manager
document.addEventListener('DOMContentLoaded', () => {
    window.googleContactsManager = new GoogleContactsManager();
});

export { GoogleContactsManager };
import api from './api.js';

class AuthManager {
    constructor() {
        this.currentUser = null;
        this.isAuthenticated = false;
        this.authStateListeners = new Set();
        
        this.loginForm = document.getElementById('login-form');
        this.registerForm = document.getElementById('register-form');
        this.loginBtn = document.getElementById('login-btn');
        this.registerBtn = document.getElementById('register-btn');
        this.logoutBtn = document.getElementById('logout-btn');
        this.userInfo = document.getElementById('user-info');
        this.username = document.getElementById('username');
        
        this.initializeAuth();
        this.setupEventListeners();
    }

    initializeAuth() {
        const token = localStorage.getItem('token');
        if (token) {
            this.verifyToken();
        }
    }

    setupEventListeners() {
        this.loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            
            try {
                await this.login(email, password);
                this.loginForm.reset();
                this.loginForm.classList.add('hidden');
                this.showToast('Successfully logged in', 'success');
            } catch (error) {
                this.showToast(error.message, 'error');
            }
        });

        this.registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const username = document.getElementById('register-username').value;
            const email = document.getElementById('register-email').value;
            const password = document.getElementById('register-password').value;
            const confirmPassword = document.getElementById('register-confirm-password').value;

            if (password !== confirmPassword) {
                this.showToast('Passwords do not match', 'error');
                return;
            }

            const userData = {
                username,
                email,
                password,
                password_confirm: confirmPassword
            };

            try {
                await this.register(userData);
                this.registerForm.reset();
                this.registerForm.classList.add('hidden');
                this.showToast('Registration successful. Please log in.', 'success');
            } catch (error) {
                this.showToast(error.message, 'error');
            }
        });

        this.loginBtn.addEventListener('click', () => {
            this.registerForm.classList.add('hidden');
            this.loginForm.classList.toggle('hidden');
        });

        this.registerBtn.addEventListener('click', () => {
            this.loginForm.classList.add('hidden');
            this.registerForm.classList.toggle('hidden');
        });

        this.logoutBtn.addEventListener('click', () => this.logout());
    }

    async login(email, password) {
        try {
            const response = await api.login(email, password);
            const userData = await api.request('/auth/test-token');
            const userId = userData.id || this.parseJwt(response.access_token).user_id;
            this.currentUser = {
                ...userData,
                id: userId
            };
            this.isAuthenticated = true;
            this.updateUI();
            this.notifyAuthStateChange();
        } catch (error) {
            throw new Error('Login failed: ' + error.message);
        }
    }

    parseJwt(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (error) {
            return {};
        }
    }

    async register(userData) {
        try {
            await api.register(userData);
        } catch (error) {
            throw new Error('Registration failed: ' + error.message);
        }
    }

    async logout() {
        try {
            await api.logout();
            this.currentUser = null;
            this.isAuthenticated = false;
            this.updateUI();
            this.notifyAuthStateChange();
            this.showToast('Successfully logged out', 'success');
        } catch (error) {
            this.showToast('Logout failed: ' + error.message, 'error');
        }
    }

    async verifyToken() {
        try {
            const userData = await api.request('/auth/test-token');
            const userId = userData.id;
            this.currentUser = {
                ...userData,
                id: userId
            };
            this.isAuthenticated = true;
            this.updateUI();
            this.notifyAuthStateChange();
        } catch (error) {
            this.logout();
        }
    }

    updateUI() {
        if (this.isAuthenticated && this.currentUser) {
            this.loginBtn.classList.add('hidden');
            this.registerBtn.classList.add('hidden');
            this.logoutBtn.classList.remove('hidden');
            this.userInfo.classList.remove('hidden');
            this.username.textContent = this.currentUser.username;
            this.loginForm.classList.add('hidden');
            this.registerForm.classList.add('hidden');
        } else {
            this.loginBtn.classList.remove('hidden');
            this.registerBtn.classList.remove('hidden');
            this.logoutBtn.classList.add('hidden');
            this.userInfo.classList.add('hidden');
            this.username.textContent = '';
        }
    }

    onAuthStateChange(listener) {
        this.authStateListeners.add(listener);
    }

    offAuthStateChange(listener) {
        this.authStateListeners.delete(listener);
    }

    notifyAuthStateChange() {
        this.authStateListeners.forEach(listener => {
            try {
                listener(this.isAuthenticated, this.currentUser);
            } catch (error) {
            }
        });
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        const container = document.getElementById('toast-container');
        container.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
}

const auth = new AuthManager();
export default auth;
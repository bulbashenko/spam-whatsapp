class ApiClient {
    constructor() {
        this.baseUrl = '/api/v1';
        this.token = localStorage.getItem('token');
    }

    setToken(token) {
        this.token = token;
        localStorage.setItem('token', token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem('token');
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...(this.token && { 'Authorization': `Bearer ${this.token}` }),
            ...options.headers
        };

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'API request failed');
            }

            return await response.json();
        } catch (error) {
            throw error;
        }
    }

    async login(email, password) {
        const formData = new FormData();
        formData.append('username', email);
        formData.append('password', password);

        const response = await fetch(`${this.baseUrl}/auth/login`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    async register(userData) {
        const registerData = {
            email: userData.email,
            password: userData.password,
            password_confirm: userData.password_confirm
        };

        const response = await fetch(`${this.baseUrl}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(registerData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Registration failed');
        }

        return await response.json();
    }

    async logout() {
        await this.request('/auth/logout', { method: 'POST' });
        this.clearToken();
    }

    async createSearch(searchData) {
        return this.request('/business/search', {
            method: 'POST',
            body: JSON.stringify(searchData)
        });
    }

    async getSearch(searchId) {
        return this.request(`/business/search/${searchId}`);
    }

    async getSearchResults(searchId, page = 1, per_page = 10) {
        return this.request(`/business/search/${searchId}/results?page=${page}&per_page=${per_page}`);
    }

    async getSearchStats() {
        return this.request('/business/stats');
    }

    async downloadSearchResults(searchId, format) {
        try {
            const response = await fetch(`${this.baseUrl}/business/search/${searchId}/export/${format}`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `Export to ${format.toUpperCase()} failed`);
            }

            const contentDisposition = response.headers.get('Content-Disposition');
            const filename = contentDisposition
                ? contentDisposition.split('filename=')[1].replace(/"/g, '')
                : `business_search_results.${format}`;

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);

            return true;
        } catch (error) {
            throw error;
        }
    }

    async exportToCsv(searchId) {
        return this.downloadSearchResults(searchId, 'csv');
    }

    async exportToXlsx(searchId) {
        return this.downloadSearchResults(searchId, 'xlsx');
    }

    async getLocationPredictions(query) {
        return this.request(`/business/locations/predict?query=${encodeURIComponent(query)}`);
    }

    async getBusinessDetails(businessId) {
        return this.request(`/business/details/${businessId}`);
    }
}

const api = new ApiClient();
export default api;
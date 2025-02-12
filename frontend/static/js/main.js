import auth from './auth.js';
import search from './search.js';
import ui from './ui.js';

class App {
    constructor() {
        this.initializeApp();
    }

    async initializeApp() {
        try {
            ui.setPageTitle('Home');
            this.setupAuthStateHandler();
            this.setupErrorHandling();
            this.handleDeepLinking();
            document.body.classList.remove('loading');
        } catch (error) {
            ui.showToast('Failed to initialize application', 'error');
        }
    }

    setupAuthStateHandler() {
        auth.onAuthStateChange((isAuthenticated, user) => {
            document.body.classList.toggle('authenticated', isAuthenticated);
            
            if (isAuthenticated) {
                this.loadUserData(user);
            } else {
                this.clearUserData();
            }
        });
    }

    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            ui.showToast('An unexpected error occurred', 'error');
        });

        window.addEventListener('unhandledrejection', (event) => {
            ui.showToast('An unexpected error occurred', 'error');
        });

        window.addEventListener('online', () => {
            ui.showToast('Connection restored', 'success');
        });

        window.addEventListener('offline', () => {
            ui.showToast('Connection lost', 'error');
        });
    }

    handleDeepLinking() {
        const params = new URLSearchParams(window.location.search);
        
        if (params.has('q') && params.has('location')) {
            const searchQuery = params.get('q');
            const location = params.get('location');
            const radius = params.get('radius') || 5;

            document.getElementById('business-type').value = searchQuery;
            document.getElementById('location').value = location;
            document.getElementById('radius').value = radius;

            if (auth.isAuthenticated) {
                search.startSearch();
            }
        }
    }

    async loadUserData(user) {
        try {
            const searchStats = await search.getSearchStats();
            if (searchStats.most_searched_types.length > 0) {
                this.displayRecentSearches(searchStats.most_searched_types);
            }
        } catch (error) {
            ui.showToast('Failed to load user data', 'error');
        }
    }

    clearUserData() {
        document.querySelectorAll('.user-specific').forEach(element => {
            element.innerHTML = '';
            element.classList.add('hidden');
        });
    }

    displayRecentSearches(searches) {
        const container = document.createElement('div');
        container.className = 'recent-searches user-specific';
        
        const title = document.createElement('h3');
        title.textContent = 'Recent Searches';
        container.appendChild(title);

        const list = document.createElement('ul');
        searches.forEach(search => {
            const item = document.createElement('li');
            item.innerHTML = `
                <span>${search.type}</span>
                <small>(${search.count} searches)</small>
                <button class="btn" onclick="handleRecentSearch('${search.type}')">
                    <i class="fas fa-search"></i>
                </button>
            `;
            list.appendChild(item);
        });
        container.appendChild(list);

        const searchForm = document.getElementById('search-form');
        searchForm.parentNode.insertBefore(container, searchForm);
    }
}

const app = new App();

window.handleRecentSearch = (query) => {
    document.getElementById('business-type').value = query;
    if (auth.isAuthenticated) {
        search.startSearch();
    }
};
import auth from './auth.js';
import search from './search.js';
import ui from './ui.js';
import { GoogleContactsManager } from './google.js';

/**
 * Main Application Class
 * Enhanced with modern libraries integration
 */
class App {
    constructor() {
        this.initializeApp();
        this.charts = {};
    }

    async initializeApp() {
        try {
            ui.setPageTitle('Home');
            this.setupAuthStateHandler();
            this.setupErrorHandling();
            this.handleDeepLinking();
            this.setupBootstrapComponents();
            
            // Initialize Google Contacts manager
            window.googleContactsManager = new GoogleContactsManager();
            
            // Create Alpine data store for reactive state management
            this.initializeAlpineData();
            
            document.body.classList.remove('loading');
            document.body.classList.add('fade-in');
            
            // Show welcome message with SweetAlert2
            this.showWelcomeMessage();
        } catch (error) {
            console.error('Application initialization error:', error);
            this.showAlert('Failed to initialize application', 'error');
        }
    }

    setupAuthStateHandler() {
        auth.onAuthStateChange((isAuthenticated, user) => {
            document.body.classList.toggle('authenticated', isAuthenticated);
            
            if (isAuthenticated) {
                // Delay loading user data to ensure UI is ready
                setTimeout(() => {
                    this.loadUserData(user);
                }, 100);
                
                // Only update Alpine store if it exists
                if (window.Alpine && Alpine.store) {
                    Alpine.store('userData').isAuthenticated = true;
                    Alpine.store('userData').userInfo = user;
                }
            } else {
                this.clearUserData();
                
                // Only update Alpine store if it exists
                if (window.Alpine && Alpine.store) {
                    Alpine.store('userData').isAuthenticated = false;
                    Alpine.store('userData').userInfo = null;
                }
            }
        });
    }

    setupErrorHandling() {
        window.addEventListener('error', (event) => {
            this.showAlert('An unexpected error occurred', 'error');
        });

        window.addEventListener('unhandledrejection', (event) => {
            this.showAlert('An unexpected error occurred', 'error');
        });

        window.addEventListener('online', () => {
            this.showAlert('Connection restored', 'success');
        });

        window.addEventListener('offline', () => {
            this.showAlert('Connection lost', 'error');
        });
    }

    setupBootstrapComponents() {
        // Initialize all Bootstrap tooltips
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => 
            new bootstrap.Tooltip(tooltipTriggerEl));

        // Initialize popovers
        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        const popoverList = [...popoverTriggerList].map(popoverTriggerEl => 
            new bootstrap.Popover(popoverTriggerEl));
            
        // Add Bootstrap form validation
        const forms = document.querySelectorAll('.needs-validation');
        Array.from(forms).forEach(form => {
            form.addEventListener('submit', event => {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
                form.classList.add('was-validated');
            }, false);
        });
    }

    initializeAlpineData() {
        // Create Alpine.js data stores for reactive state management
        Alpine.store('userData', {
            isAuthenticated: auth.isAuthenticated,
            userInfo: null,
            searchStats: null
        });
        
        Alpine.store('appState', {
            currentSection: 'search',
            isLoading: false,
            activePage: 1,
            totalPages: 1
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
            // Check if search.getSearchStats exists
            if (typeof search.getSearchStats === 'function') {
                // Original functionality if the method exists
                const searchStats = await search.getSearchStats();
                
                // Store in Alpine data store
                if (window.Alpine && Alpine.store) {
                    Alpine.store('userData').searchStats = searchStats;
                }
                
                if (searchStats && searchStats.most_searched_types && searchStats.most_searched_types.length > 0) {
                    this.displayRecentSearches(searchStats.most_searched_types);
                    this.createSearchStatsChart(searchStats);
                }
            } else {
                // Graceful fallback if method is missing
                console.info('Search stats functionality not available');
                
                // Create empty search stats to avoid errors elsewhere
                const emptyStats = { most_searched_types: [] };
                
                // Store in Alpine data store if available
                if (window.Alpine && Alpine.store) {
                    Alpine.store('userData').searchStats = emptyStats;
                }
            }
        } catch (error) {
            console.error('Failed to load user data:', error);
            // Use UI.showAlert if available, otherwise use console
            if (this.showAlert) {
                this.showAlert('Failed to load user data', 'error');
            } else {
                console.error('Failed to load user data:', error);
            }
        }
    }

    clearUserData() {
        document.querySelectorAll('.user-specific').forEach(element => {
            element.innerHTML = '';
            element.classList.add('hidden');
        });
        
        // Clear any charts
        if (this.charts.searchStats) {
            this.charts.searchStats.destroy();
        }
    }

    displayRecentSearches(searches) {
        const container = document.createElement('div');
        container.className = 'recent-searches user-specific card mb-4';
        
        container.innerHTML = `
            <div class="card-header bg-primary text-white">
                <h3 class="h5 mb-0">Recent Searches</h3>
            </div>
            <div class="card-body">
                <ul class="list-group">
                    ${searches.map(search => `
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div>
                                <span class="fw-medium">${search.type}</span>
                                <span class="badge bg-primary rounded-pill ms-2">${search.count}</span>
                            </div>
                            <button class="btn btn-sm btn-outline-primary" onclick="handleRecentSearch('${search.type}')">
                                <i class="fas fa-search"></i> Search
                            </button>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;

        const searchForm = document.getElementById('search-form');
        searchForm.parentNode.insertBefore(container, searchForm);
    }

    createSearchStatsChart(searchStats) {
        const canvas = document.createElement('canvas');
        canvas.id = 'searchStatsChart';
        canvas.className = 'user-specific mb-4';
        canvas.height = 250;
        
        const container = document.createElement('div');
        container.className = 'card';
        
        const cardHeader = document.createElement('div');
        cardHeader.className = 'card-header bg-primary text-white';
        cardHeader.innerHTML = '<h3 class="h5 mb-0">Search Analytics</h3>';
        
        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';
        cardBody.appendChild(canvas);
        
        container.appendChild(cardHeader);
        container.appendChild(cardBody);
        
        const searchForm = document.getElementById('search-form');
        const recentSearches = document.querySelector('.recent-searches');
        
        if (recentSearches) {
            recentSearches.parentNode.insertBefore(container, recentSearches.nextSibling);
        } else {
            searchForm.parentNode.insertBefore(container, searchForm);
        }
        
        // Create chart with Chart.js
        const ctx = canvas.getContext('2d');
        this.charts.searchStats = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: searchStats.most_searched_types.map(item => item.type),
                datasets: [{
                    label: 'Searches',
                    data: searchStats.most_searched_types.map(item => item.count),
                    backgroundColor: 'rgba(79, 70, 229, 0.7)',
                    borderColor: 'rgba(79, 70, 229, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                    },
                    title: {
                        display: true,
                        text: 'Most Frequently Searched Business Types'
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `${context.parsed.y} searches`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }

    showAlert(message, type = 'info', title = '') {
        // Use SweetAlert2 for better alerts
        const iconMap = {
            'success': 'success',
            'error': 'error',
            'warning': 'warning',
            'info': 'info'
        };
        
        const toast = Swal.mixin({
            toast: true,
            position: 'bottom-end',
            showConfirmButton: false,
            timer: 3000,
            timerProgressBar: true,
            didOpen: (toast) => {
                toast.addEventListener('mouseenter', Swal.stopTimer);
                toast.addEventListener('mouseleave', Swal.resumeTimer);
            }
        });
        
        toast.fire({
            icon: iconMap[type] || 'info',
            title: title || message
        });
        
        // Also use the original toast system for backward compatibility
        ui.showToast(message, type);
    }
    
    showWelcomeMessage() {
        if (localStorage.getItem('welcomeShown') !== 'true') {
            setTimeout(() => {
                Swal.fire({
                    title: 'Welcome to Business Search',
                    text: 'Find business contacts and save them directly to Google Contacts.',
                    icon: 'info',
                    confirmButtonText: 'Get Started',
                    confirmButtonColor: '#4f46e5',
                    showClass: {
                        popup: 'animate__animated animate__fadeInDown'
                    },
                    hideClass: {
                        popup: 'animate__animated animate__fadeOutUp'
                    }
                });
                localStorage.setItem('welcomeShown', 'true');
            }, 1000);
        }
    }
}

const app = new App();

// Global handlers
window.handleRecentSearch = (query) => {
    document.getElementById('business-type').value = query;
    if (auth.isAuthenticated) {
        search.startSearch();
    } else {
        app.showAlert('Please login to start a search', 'warning');
    }
};

// Add global access to the app for debugging
window.app = app;
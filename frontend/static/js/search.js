import api from './api.js';
import auth from './auth.js';

class SearchManager {
    constructor() {
        this.currentSearch = null;
        this.currentPage = 1;
        this.perPage = 10;
        this.searchResults = [];
        this.totalResults = 0;
        this.locationDebounceTimer = null;
        this.pollInterval = null;
        
        this.detailsModal = document.createElement('div');
        this.detailsModal.className = 'modal';
        this.detailsModal.innerHTML = `
            <div class="modal-content">
                <span class="close">&times;</span>
                <div id="business-details"></div>
            </div>
        `;
        document.body.appendChild(this.detailsModal);
        
        const closeBtn = this.detailsModal.querySelector('.close');
        closeBtn.addEventListener('click', () => {
            this.detailsModal.style.display = 'none';
        });
        
        this.detailsModal.addEventListener('click', (e) => {
            if (e.target === this.detailsModal) {
                this.detailsModal.style.display = 'none';
            }
        });
        
        this.searchSection = document.getElementById('search-section');
        this.searchForm = document.getElementById('search-form');
        this.progressContainer = document.getElementById('progress-container');
        this.progressBar = document.getElementById('progress');
        this.progressText = document.getElementById('progress-text');
        this.resultsContainer = document.getElementById('results-container');
        this.resultsTable = document.getElementById('results-table');
        this.resultsBody = document.getElementById('results-body');
        this.tableSearch = document.getElementById('table-search');
        this.exportCsvBtn = document.getElementById('export-csv');
        this.exportXlsxBtn = document.getElementById('export-xlsx');
        this.prevPageBtn = document.getElementById('prev-page');
        this.nextPageBtn = document.getElementById('next-page');
        this.pageInfo = document.getElementById('page-info');
        this.locationInput = document.getElementById('location');

        this.locationSuggestions = document.createElement('div');
        this.locationSuggestions.className = 'location-suggestions';
        this.locationSuggestions.style.display = 'none';
        this.locationInput.closest('.location-input-container').appendChild(this.locationSuggestions);
        
        this.setupEventListeners();
    }

    setupEventListeners() {
        this.locationInput.addEventListener('input', () => {
            clearTimeout(this.locationDebounceTimer);
            this.locationDebounceTimer = setTimeout(() => {
                this.handleLocationInput();
            }, 300);
        });

        this.locationInput.addEventListener('blur', () => {
            setTimeout(() => {
                this.locationSuggestions.style.display = 'none';
            }, 200);
        });

        this.searchForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.startSearch();
        });

        this.tableSearch.addEventListener('input', () => {
            this.filterResults();
        });

        this.exportCsvBtn.addEventListener('click', async () => {
            await this.exportResults('csv');
        });

        this.exportXlsxBtn.addEventListener('click', async () => {
            await this.exportResults('xlsx');
        });

        this.prevPageBtn.addEventListener('click', () => {
            if (this.currentPage > 1) {
                this.currentPage--;
                this.loadResults();
            }
        });

        this.nextPageBtn.addEventListener('click', () => {
            const maxPage = Math.ceil(this.totalResults / this.perPage);
            if (this.currentPage < maxPage) {
                this.currentPage++;
                this.loadResults();
            }
        });

        auth.onAuthStateChange((isAuthenticated) => {
            this.searchSection.classList.toggle('hidden', !isAuthenticated);
            if (!isAuthenticated) {
                this.resetSearch();
            }
        });
    }

    async pollSearchStatus() {
        if (!this.currentSearch) return;
        
        try {
            const search = await api.getSearch(this.currentSearch.id);
            
            if (search.status === 'completed') {
                clearInterval(this.pollInterval);
                this.progressText.textContent = 'Search completed!';
                await this.loadResults();
                this.progressContainer.classList.add('hidden');
                this.resultsContainer.classList.remove('hidden');
            } else if (search.status === 'failed') {
                clearInterval(this.pollInterval);
                this.showError('Search failed');
            } else {
                const progress = search.progress || 0;
                this.updateProgress(progress, `Found ${search.results_count || 0} results...`);
            }
        } catch (error) {
            clearInterval(this.pollInterval);
            this.showError('Failed to check search status');
        }
    }

    async startSearch() {
        const businessType = document.getElementById('business-type').value;
        const location = document.getElementById('location').value;
        const radius = document.getElementById('radius').value;

        try {
            this.resetSearch();
            this.progressContainer.classList.remove('hidden');
            this.resultsContainer.classList.add('hidden');
            this.progressBar.style.width = '0%';
            this.progressText.textContent = 'Starting search...';

            this.currentSearch = await api.createSearch({
                business_type: businessType,
                location: location,
                radius: parseInt(radius) * 1000
            });

            this.updateProgress(0, 'Search started...');
            this.pollInterval = setInterval(() => this.pollSearchStatus(), 2000);
        } catch (error) {
            this.showError('Failed to start search: ' + error.message);
        }
    }

    async loadResults() {
        if (!this.currentSearch) return;

        try {
            const response = await api.getSearchResults(
                this.currentSearch.id,
                this.currentPage,
                this.perPage
            );

            this.searchResults = response.items || [];
            this.totalResults = response.total || 0;
            
            this.renderResults();
            this.updatePagination();
            
            this.progressContainer.classList.add('hidden');
            this.resultsContainer.classList.remove('hidden');
        } catch (error) {
            this.showError('Failed to load results: ' + error.message);
        }
    }

    renderResults() {
        this.resultsBody.innerHTML = '';
        
        this.searchResults.forEach(business => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${business.name}</td>
                <td>${business.formatted_address}</td>
                <td>${business.rating || 'N/A'} ${business.rating ? `(${business.user_ratings_total})` : ''}</td>
                <td>${business.business_status || 'N/A'}</td>
                <td>
                    ${business.website ? `
                        <a href="${business.website}" target="_blank" class="btn">
                            <i class="fas fa-external-link-alt"></i>
                        </a>
                    ` : ''}
                    <button class="btn" onclick="showDetails('${business.id}')">
                        <i class="fas fa-info-circle"></i>
                    </button>
                </td>
            `;
            this.resultsBody.appendChild(row);
        });
    }

    filterResults() {
        const searchTerm = this.tableSearch.value.toLowerCase();
        const rows = this.resultsBody.getElementsByTagName('tr');

        Array.from(rows).forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    }

    updatePagination() {
        const maxPage = Math.ceil(this.totalResults / this.perPage);
        this.pageInfo.textContent = `Page ${this.currentPage} of ${maxPage}`;
        this.prevPageBtn.disabled = this.currentPage === 1;
        this.nextPageBtn.disabled = this.currentPage === maxPage;
    }

    updateProgress(progress, message) {
        const progressValue = Math.min(Math.max(progress, 0), 100);
        requestAnimationFrame(() => {
            this.progressBar.style.width = `${progressValue}%`;
            this.progressText.textContent = message;
        });
    }

    showProgress() {
        requestAnimationFrame(() => {
            this.progressContainer.classList.remove('hidden');
            this.resultsContainer.classList.add('hidden');
            this.progressBar.style.width = '0%';
        });
    }

    showError(message) {
        this.progressContainer.classList.add('hidden');
        this.showToast(message, 'error');
    }

    resetSearch() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.currentSearch = null;
        this.currentPage = 1;
        this.searchResults = [];
        this.totalResults = 0;
        this.progressBar.style.width = '0%';
        this.progressText.textContent = '';
        this.resultsContainer.classList.add('hidden');
    }

    async exportResults(format) {
        if (!this.currentSearch) {
            this.showToast('No active search to export', 'error');
            return;
        }

        const button = format === 'csv' ? this.exportCsvBtn : this.exportXlsxBtn;
        const originalText = button.innerHTML;

        try {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Exporting...';

            if (format === 'csv') {
                await api.exportToCsv(this.currentSearch.id);
            } else {
                await api.exportToXlsx(this.currentSearch.id);
            }

            this.showToast(`Export to ${format.toUpperCase()} completed`, 'success');
        } catch (error) {
            this.showToast(`Export failed: ${error.message}`, 'error');
        } finally {
            button.disabled = false;
            button.innerHTML = originalText;
        }
    }

    async showDetails(businessId) {
        try {
            const details = await api.getBusinessDetails(businessId);
            const detailsHtml = `
                <h2>${details.name}</h2>
                <p><strong>Address:</strong> ${details.formatted_address}</p>
                <p><strong>Phone:</strong> ${details.formatted_phone_number || 'No data'}</p>
                <p><strong>International Phone:</strong> ${details.international_phone_number || 'No data'}</p>
                <p><strong>Rating:</strong> ${details.rating || 'No data'} (${details.user_ratings_total || 0} reviews)</p>
                <p><strong>Price Level:</strong> ${details.price_level ? '€'.repeat(details.price_level) : 'No data'}</p>
                <p><strong>Status:</strong> ${details.business_status || 'No data'}</p>
                ${details.website ? `<p><strong>Website:</strong> <a href="${details.website}" target="_blank">${details.website}</a></p>` : ''}
                ${details.url ? `<p><strong>Google Maps:</strong> <a href="${details.url}" target="_blank">Open in Google Maps</a></p>` : ''}
                
                ${details.weekday_text ? `
                    <h3>Opening Hours:</h3>
                    <ul>
                        ${details.weekday_text.map(day => `<li>${day}</li>`).join('')}
                    </ul>
                ` : ''}
                
                ${details.reviews ? `
                    <h3>Reviews:</h3>
                    <div class="reviews">
                        ${details.reviews.map(review => `
                            <div class="review">
                                <p><strong>${review.author_name}</strong> - ${review.rating} ⭐</p>
                                <p>${review.text}</p>
                                <small>${review.relative_time_description}</small>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}
            `;
            
            document.getElementById('business-details').innerHTML = detailsHtml;
            this.detailsModal.style.display = 'block';
            
        } catch (error) {
            this.showToast(error.message, 'error');
        }
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

    async handleLocationInput() {
        const query = this.locationInput.value.trim();
        if (query.length < 2) {
            this.locationSuggestions.style.display = 'none';
            return;
        }

        try {
            const { predictions } = await api.getLocationPredictions(query);
            if (predictions && predictions.length > 0) {
                this.showLocationSuggestions(predictions);
            } else {
                this.locationSuggestions.style.display = 'none';
            }
        } catch (error) {
            this.locationSuggestions.style.display = 'none';
        }
    }

    showLocationSuggestions(predictions) {
        this.locationSuggestions.innerHTML = '';
        predictions.forEach(prediction => {
            const div = document.createElement('div');
            div.className = 'location-suggestion';
            div.innerHTML = `
                <div class="main-text">${prediction.main_text}</div>
                <div class="secondary-text">${prediction.secondary_text}</div>
            `;
            div.addEventListener('click', () => {
                this.locationInput.value = prediction.description;
                this.locationSuggestions.style.display = 'none';
            });
            this.locationSuggestions.appendChild(div);
        });
        this.locationSuggestions.style.display = 'block';
    }
}

const search = new SearchManager();
export default search;

window.showDetails = (businessId) => {
    search.showDetails(businessId);
};
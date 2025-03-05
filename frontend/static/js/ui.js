/**
 * Enhanced UI Manager
 * Uses Bootstrap, SweetAlert2, and Alpine.js for modern UI
 */
class UIManager {
    constructor() {
        // Ensure toast container exists
        this.toastContainer = document.getElementById('toast-container');
        if (!this.toastContainer) {
            // Create toast container if it doesn't exist
            this.toastContainer = document.createElement('div');
            this.toastContainer.id = 'toast-container';
            document.body.appendChild(this.toastContainer);
        }
        this.modals = {};
        this.setupGlobalHandlers();
        this.setupBootstrapIntegration();
    }

    setupGlobalHandlers() {
        // Handle form submissions across the application
        document.addEventListener('submit', (e) => {
            if (e.target.tagName === 'FORM') {
                this.handleFormSubmit(e.target);
            }
        });

        // Table sorting functionality
        document.addEventListener('click', (e) => {
            const target = e.target.closest('th');
            if (target && !target.classList.contains('no-sort')) {
                this.handleTableSort(target);
            }
        });
        
        // Handle navigation link clicks
        document.addEventListener('click', (e) => {
            const navBtn = e.target.closest('.nav-links .btn');
            if (navBtn) {
                this.handleNavigation(navBtn);
            }
        });
    }

    setupBootstrapIntegration() {
        // Setup global Bootstrap event handlers
        document.addEventListener('shown.bs.modal', (e) => {
            // Focus first input in modal
            const firstInput = e.target.querySelector('input, textarea, select');
            if (firstInput) firstInput.focus();
        });
        
        // Setup global dropdown handlers
        document.addEventListener('click', (e) => {
            const dropdownToggle = e.target.closest('[data-bs-toggle="dropdown"]');
            if (dropdownToggle) {
                const dropdown = new bootstrap.Dropdown(dropdownToggle);
            }
        });
    }

    /**
     * Enhanced toast notification using SweetAlert2
     * with fallback to custom toast implementation
     */
    showToast(message, type = 'info', duration = 3000) {
        // First try to use SweetAlert2 if available
        if (window.Swal) {
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
                timer: duration,
                timerProgressBar: true,
                didOpen: (toast) => {
                    toast.addEventListener('mouseenter', Swal.stopTimer);
                    toast.addEventListener('mouseleave', Swal.resumeTimer);
                }
            });
            
            toast.fire({
                icon: iconMap[type] || 'info',
                title: message
            });
            
        } else {
            try {
                // Check if container exists every time we show a toast
                this.toastContainer = document.getElementById('toast-container');
                if (!this.toastContainer) {
                    // Create toast container if it doesn't exist
                    this.toastContainer = document.createElement('div');
                    this.toastContainer.id = 'toast-container';
                    this.toastContainer.style.position = 'fixed';
                    this.toastContainer.style.bottom = '20px';
                    this.toastContainer.style.right = '20px';
                    this.toastContainer.style.zIndex = '9999';
                    
                    // Only append if document.body exists
                    if (document.body) {
                        document.body.appendChild(this.toastContainer);
                    } else {
                        // If body doesn't exist yet, wait for DOMContentLoaded
                        console.warn('Toast container created but document.body not available yet');
                        return; // Skip showing toast this time
                    }
                }
                
                // Fallback to custom implementation
                const toast = document.createElement('div');
                toast.className = `toast toast-${type}`;
                toast.textContent = message;
                
                this.toastContainer.appendChild(toast);
                
                // Force reflow
                toast.offsetHeight;
                toast.classList.add('show');
                
                setTimeout(() => {
                    toast.classList.remove('show');
                    setTimeout(() => toast.remove(), 300);
                }, duration);
            } catch (error) {
                console.warn('Failed to show toast:', error);
            }
        }
    }

    /**
     * Show a confirmation dialog with SweetAlert2 or fallback to confirm()
     */
    async confirmAction(title, message, confirmText = 'Yes', cancelText = 'Cancel', type = 'warning') {
        if (window.Swal) {
            const result = await Swal.fire({
                title: title,
                text: message,
                icon: type,
                showCancelButton: true,
                confirmButtonColor: '#4f46e5',
                cancelButtonColor: '#6b7280',
                confirmButtonText: confirmText,
                cancelButtonText: cancelText
            });
            
            return result.isConfirmed;
        } else {
            return confirm(message);
        }
    }

    /**
     * Show an input dialog with SweetAlert2
     */
    async promptInput(title, inputLabel, placeholder = '', defaultValue = '') {
        if (window.Swal) {
            const result = await Swal.fire({
                title: title,
                input: 'text',
                inputLabel: inputLabel,
                inputPlaceholder: placeholder,
                inputValue: defaultValue,
                showCancelButton: true,
                inputValidator: (value) => {
                    if (!value) {
                        return 'Please enter a value!';
                    }
                }
            });
            
            return result.value;
        } else {
            return prompt(inputLabel, defaultValue);
        }
    }

    /**
     * Handle form submissions with enhanced styling
     */
    handleFormSubmit(form) {
        if (form.classList.contains('prevent-double-submit')) {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                const originalText = submitButton.innerHTML;
                const originalWidth = submitButton.offsetWidth;
                
                // Store original width to prevent layout shift
                submitButton.style.minWidth = `${originalWidth}px`;
                submitButton.disabled = true;
                
                // Use Bootstrap spinner
                submitButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...`;

                // Re-enable after submission
                setTimeout(() => {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalText;
                    submitButton.style.minWidth = '';
                }, 5000);
            }
        }
    }

    /**
     * Enhanced table sorting
     */
    handleTableSort(header) {
        const table = header.closest('table');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const columnIndex = Array.from(header.parentNode.children).indexOf(header);
        const isNumeric = header.classList.contains('numeric');
        const isDate = header.classList.contains('date');

        const isAscending = header.classList.toggle('asc');
        header.classList.toggle('desc', !isAscending);

        // Clear other headers' sort classes
        header.parentNode.querySelectorAll('th').forEach(th => {
            if (th !== header) {
                th.classList.remove('asc', 'desc');
            }
        });

        // Update sort icon if using Bootstrap icons
        const icon = header.querySelector('.sort-icon');
        if (icon) {
            icon.className = `sort-icon fas fa-sort-${isAscending ? 'up' : 'down'}`;
        }

        // Sort rows
        rows.sort((a, b) => {
            const aValue = a.children[columnIndex].textContent.trim();
            const bValue = b.children[columnIndex].textContent.trim();

            if (isNumeric) {
                return (parseFloat(aValue) - parseFloat(bValue)) * (isAscending ? 1 : -1);
            } else if (isDate) {
                return (new Date(aValue) - new Date(bValue)) * (isAscending ? 1 : -1);
            } else {
                return aValue.localeCompare(bValue) * (isAscending ? 1 : -1);
            }
        });

        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));
        
        // Highlight sorted column
        const cells = table.querySelectorAll(`td:nth-child(${columnIndex + 1})`);
        cells.forEach(cell => {
            cell.classList.add('sorted');
            setTimeout(() => cell.classList.remove('sorted'), 1000);
        });
    }

    /**
     * Handle main navigation
     */
    handleNavigation(navBtn) {
        // Update active state for nav buttons
        document.querySelectorAll('.nav-links .btn').forEach(btn => {
            btn.classList.remove('active');
        });
        navBtn.classList.add('active');
        
        // Update Alpine.js store if available
        if (window.Alpine && Alpine.store('appState')) {
            Alpine.store('appState').currentSection = navBtn.id.replace('-nav-btn', '');
        }
        
        // Show corresponding section
        const sectionId = navBtn.id.replace('-nav-btn', '-section');
        document.querySelectorAll('.container').forEach(container => {
            container.classList.add('hidden');
        });
        
        const section = document.getElementById(sectionId);
        if (section) {
            section.classList.remove('hidden');
            section.classList.add('fade-in');
        }
    }

    /**
     * Show loading spinner - Bootstrap style if available
     */
    showLoadingSpinner(container, size = 'md') {
        // Remove any existing spinners
        this.removeLoadingSpinner(container);
        
        // Create spinner with Bootstrap classes if available
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        
        if (document.querySelector('link[href*="bootstrap"]')) {
            // Bootstrap style spinner
            spinner.innerHTML = `
                <div class="d-flex justify-content-center align-items-center p-4">
                    <div class="spinner-border text-primary spinner-border-${size}" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            `;
        } else {
            // Fallback
            spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        }
        
        container.appendChild(spinner);
        return spinner;
    }

    /**
     * Remove loading spinner
     */
    removeLoadingSpinner(container) {
        const spinner = container.querySelector('.loading-spinner');
        if (spinner) {
            spinner.remove();
        }
    }

    /**
     * Create a Bootstrap modal if Bootstrap is available
     */
    createModal(id, title, content, options = {}) {
        // Check if we already have this modal
        if (document.getElementById(id)) {
            return this.getModal(id);
        }
        
        // Create a Bootstrap modal if available, otherwise create a custom one
        const modal = document.createElement('div');
        modal.id = id;
        modal.className = 'modal fade';
        modal.setAttribute('tabindex', '-1');
        modal.setAttribute('aria-labelledby', `${id}Label`);
        modal.setAttribute('aria-hidden', 'true');
        
        modal.innerHTML = `
            <div class="modal-dialog ${options.size || 'modal-lg'}">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="${id}Label">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        ${content}
                    </div>
                    ${options.footer ? `
                        <div class="modal-footer">
                            ${options.footer}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Store reference to Bootstrap modal if available
        if (window.bootstrap) {
            this.modals[id] = new bootstrap.Modal(modal);
        }
        
        return this.getModal(id);
    }

    /**
     * Get a modal instance by ID
     */
    getModal(id) {
        // Return the Bootstrap modal instance if available, otherwise a simple API
        if (this.modals[id]) {
            return this.modals[id];
        }
        
        const modalElement = document.getElementById(id);
        if (!modalElement) return null;
        
        // Simple modal API for non-Bootstrap modals
        return {
            show: () => {
                modalElement.classList.remove('hidden');
                modalElement.classList.add('show');
            },
            hide: () => {
                modalElement.classList.add('hidden');
                modalElement.classList.remove('show');
            },
            toggle: () => {
                modalElement.classList.toggle('hidden');
                modalElement.classList.toggle('show');
            }
        };
    }

    /**
     * Format a date
     */
    formatDate(date, options = {}) {
        const defaultOptions = {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        
        const mergedOptions = {...defaultOptions, ...options};
        return new Date(date).toLocaleDateString('en-US', mergedOptions);
    }

    /**
     * Format a number
     */
    formatNumber(number, decimals = 2) {
        return Number(number).toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    }

    /**
     * Truncate text with ellipsis
     */
    truncateText(text, maxLength = 100) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    }

    /**
     * Set page title
     */
    setPageTitle(title) {
        document.title = `${title} - Business Search`;
    }

    /**
     * Scroll to top smoothly
     */
    scrollToTop() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }
    
    /**
     * Create a chart with Chart.js if available
     */
    createChart(canvasId, type, data, options = {}) {
        if (!window.Chart) {
            console.warn('Chart.js not available');
            return null;
        }
        
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.warn(`Canvas element with ID ${canvasId} not found`);
            return null;
        }
        
        return new Chart(canvas, {
            type,
            data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                ...options
            }
        });
    }
}

// Create UI manager instance
const ui = new UIManager();

// Named exports for commonly used UI functions
export const showToast = (message, type = 'info', duration = 3000) => ui.showToast(message, type, duration);
export const showError = (error) => ui.showToast(error.message || error, 'error', 5000);
export const confirmAction = (title, message, confirmText, cancelText, type) => 
    ui.confirmAction(title, message, confirmText, cancelText, type);
export const promptInput = (title, inputLabel, placeholder, defaultValue) => 
    ui.promptInput(title, inputLabel, placeholder, defaultValue);
export const formatDate = (date, options) => ui.formatDate(date, options);
export const formatNumber = (number, decimals) => ui.formatNumber(number, decimals);
export const truncateText = (text, maxLength) => ui.truncateText(text, maxLength);
export const createChart = (canvasId, type, data, options) => ui.createChart(canvasId, type, data, options);

// Default export
export default ui;
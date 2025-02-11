class UIManager {
    constructor() {
        this.toastContainer = document.getElementById('toast-container');
        this.setupGlobalHandlers();
    }

    setupGlobalHandlers() {
        document.addEventListener('mouseover', (e) => {
            if (e.target.classList.contains('btn')) {
                this.addButtonHoverEffect(e.target);
            }
        });

        document.addEventListener('submit', (e) => {
            if (e.target.tagName === 'FORM') {
                this.handleFormSubmit(e.target);
            }
        });

        document.querySelectorAll('th').forEach(header => {
            if (!header.classList.contains('no-sort')) {
                header.addEventListener('click', () => {
                    this.handleTableSort(header);
                });
            }
        });
    }

    showToast(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        this.toastContainer.appendChild(toast);
        
        toast.offsetHeight;
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    addButtonHoverEffect(button) {
        button.addEventListener('mouseenter', () => {
            button.style.transform = 'translateY(-2px)';
        });

        button.addEventListener('mouseleave', () => {
            button.style.transform = 'translateY(0)';
        });
    }

    handleFormSubmit(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            const originalText = submitButton.textContent;
            submitButton.disabled = true;
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

            setTimeout(() => {
                submitButton.disabled = false;
                submitButton.textContent = originalText;
            }, 5000);
        }
    }

    handleTableSort(header) {
        const table = header.closest('table');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const columnIndex = Array.from(header.parentNode.children).indexOf(header);
        const isNumeric = header.classList.contains('numeric');
        const isDate = header.classList.contains('date');

        const isAscending = header.classList.toggle('asc');
        header.classList.toggle('desc', !isAscending);

        header.parentNode.querySelectorAll('th').forEach(th => {
            if (th !== header) {
                th.classList.remove('asc', 'desc');
            }
        });

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

        rows.forEach(row => tbody.appendChild(row));
    }

    showLoadingSpinner(container) {
        const spinner = document.createElement('div');
        spinner.className = 'loading-spinner';
        spinner.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        container.appendChild(spinner);
        return spinner;
    }

    removeLoadingSpinner(spinner) {
        if (spinner && spinner.parentNode) {
            spinner.parentNode.removeChild(spinner);
        }
    }

    formatDate(date) {
        return new Date(date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    formatNumber(number, decimals = 2) {
        return Number(number).toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    }

    truncateText(text, maxLength = 100) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    }

    setPageTitle(title) {
        document.title = `${title} - Business Search`;
    }

    scrollToTop() {
        window.scrollTo({
            top: 0,
            behavior: 'smooth'
        });
    }
}

const ui = new UIManager();
export default ui;
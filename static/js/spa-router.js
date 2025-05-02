/**
 * SPA Router for Reverse Proxy Control Center
 * Handles client-side routing and content loading without page reloads
 */
class SPARouter {
    constructor() {
        this.routes = [];
        this.currentPath = window.location.pathname;
        this.contentContainer = document.getElementById('spa-content');
        this.isNavigating = false;
        
        if (this.contentContainer) {
            this.init();
        }
    }
    
    /**
     * Initialize the router
     */
    init() {
        console.log('SPA Router initialized');
        
        window.addEventListener('popstate', (event) => {
            if (event.state && event.state.path) {
                this.navigate(event.state.path, false);
            }
        });
        
        document.addEventListener('click', (event) => {
            const link = event.target.closest('a');
            
            if (!link) return;
            
            if (link.hasAttribute('target') || 
                link.hasAttribute('download') || 
                link.getAttribute('rel') === 'external' ||
                link.classList.contains('no-spa')) {
                return;
            }
            
            const href = link.getAttribute('href');
            
            if (!href || href.startsWith('#') || 
                href.startsWith('mailto:') || 
                href.startsWith('tel:') ||
                (href.startsWith('http') && !href.startsWith(window.location.origin))) {
                return;
            }
            
            event.preventDefault();
            this.navigate(href);
        });
        
        document.addEventListener('submit', (event) => {
            const form = event.target;
            
            if (form.hasAttribute('target') || 
                form.classList.contains('no-spa') ||
                form.getAttribute('enctype') === 'multipart/form-data') {
                return;
            }
            
            if (form.method.toLowerCase() === 'get') {
                event.preventDefault();
                
                const formData = new FormData(form);
                const queryString = new URLSearchParams(formData).toString();
                const action = form.getAttribute('action') || window.location.pathname;
                const url = action + (queryString ? '?' + queryString : '');
                
                this.navigate(url);
            }
        });
        
        this.setupCurrentPage();
    }
    
    /**
     * Set up the current page for SPA
     */
    setupCurrentPage() {
        if (!this.contentContainer) {
            const mainContent = document.querySelector('.container.mt-4');
            if (mainContent) {
                this.contentContainer = document.createElement('div');
                this.contentContainer.id = 'spa-content';
                
                while (mainContent.childNodes.length > 0) {
                    this.contentContainer.appendChild(mainContent.childNodes[0]);
                }
                
                mainContent.appendChild(this.contentContainer);
            }
        }
        
        this.updateActiveLinks();
    }
    
    /**
     * Navigate to a new page
     * @param {string} path - The path to navigate to
     * @param {boolean} pushState - Whether to push state to history
     */
    navigate(path, pushState = true) {
        if (this.isNavigating) return;
        this.isNavigating = true;
        
        console.log(`Navigating to: ${path}`);
        
        this.showLoading();
        
        fetch(path, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.content) {
                this.updateContent(data.content);
            }
            
            if (data.title) {
                document.title = data.title;
            }
            
            if (pushState) {
                window.history.pushState({ path }, document.title, path);
            }
            
            this.currentPath = path;
            
            this.updateActiveLinks();
            
            this.initContentScripts();
        })
        .catch(error => {
            console.error('Error loading page:', error);
            
            window.location.href = path;
        })
        .finally(() => {
            this.hideLoading();
            this.isNavigating = false;
        });
    }
    
    /**
     * Update the content container with new content
     * @param {string} content - The HTML content to display
     */
    updateContent(content) {
        this.contentContainer.classList.add('spa-fade-out');
        
        setTimeout(() => {
            this.contentContainer.innerHTML = content;
            this.contentContainer.classList.remove('spa-fade-out');
            this.contentContainer.classList.add('spa-fade-in');
            
            setTimeout(() => {
                this.contentContainer.classList.remove('spa-fade-in');
            }, 300);
        }, 300);
    }
    
    /**
     * Show loading indicator
     */
    showLoading() {
        let loader = document.getElementById('spa-loader');
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'spa-loader';
            loader.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
            document.body.appendChild(loader);
        }
        
        loader.classList.add('active');
    }
    
    /**
     * Hide loading indicator
     */
    hideLoading() {
        const loader = document.getElementById('spa-loader');
        if (loader) {
            loader.classList.remove('active');
        }
    }
    
    /**
     * Update active links in the navigation
     */
    updateActiveLinks() {
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        
        document.querySelectorAll('.nav-link').forEach(link => {
            const href = link.getAttribute('href');
            if (href === this.currentPath || 
                (this.currentPath.startsWith(href) && href !== '/')) {
                link.classList.add('active');
            }
        });
    }
    
    /**
     * Initialize any JavaScript in the new content
     */
    initContentScripts() {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            new bootstrap.Tooltip(el);
        });
        
        document.querySelectorAll('[data-bs-toggle="popover"]').forEach(el => {
            new bootstrap.Popover(el);
        });
        
        if (window.initPageScripts) {
            window.initPageScripts();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.spaRouter = new SPARouter();
});

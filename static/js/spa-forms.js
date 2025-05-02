/**
 * SPA Forms Handler for Reverse Proxy Control Center
 * Handles AJAX form submissions for the SPA
 */
class SPAForms {
    constructor() {
        this.init();
    }
    
    /**
     * Initialize the forms handler
     */
    init() {
        console.log('SPA Forms initialized');
        
        document.addEventListener('submit', (event) => {
            const form = event.target;
            
            if (form.hasAttribute('target') || 
                form.classList.contains('no-spa') ||
                form.getAttribute('enctype') === 'multipart/form-data') {
                return;
            }
            
            if (form.method.toLowerCase() === 'post') {
                event.preventDefault();
                this.submitForm(form);
            }
        });
    }
    
    /**
     * Submit a form via AJAX
     * @param {HTMLFormElement} form - The form to submit
     */
    submitForm(form) {
        if (window.spaRouter) {
            window.spaRouter.showLoading();
        }
        
        const formData = new FormData(form);
        const submitButton = form.querySelector('button[type="submit"]');
        
        if (submitButton) {
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
        }
        
        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return response.json().then(data => {
                    return {
                        ok: response.ok,
                        status: response.status,
                        data: data,
                        redirected: response.redirected,
                        url: response.url
                    };
                });
            } else {
                return {
                    ok: response.ok,
                    status: response.status,
                    redirected: response.redirected,
                    url: response.url
                };
            }
        })
        .then(result => {
            if (result.ok) {
                if (result.data && result.data.message) {
                    this.showMessage(result.data.message, 'success');
                }
                
                if (result.redirected || result.data && result.data.redirect) {
                    const redirectUrl = result.data && result.data.redirect ? result.data.redirect : result.url;
                    
                    if (window.spaRouter) {
                        window.spaRouter.navigate(redirectUrl);
                    } else {
                        window.location.href = redirectUrl;
                    }
                } else if (result.data && result.data.content) {
                    const contentContainer = document.getElementById('spa-content');
                    if (contentContainer) {
                        contentContainer.innerHTML = result.data.content;
                    }
                }
            } else {
                if (result.data && result.data.message) {
                    this.showMessage(result.data.message, 'danger');
                } else {
                    this.showMessage('An error occurred while processing your request.', 'danger');
                }
                
                if (result.data && result.data.errors) {
                    this.showValidationErrors(form, result.data.errors);
                }
            }
        })
        .catch(error => {
            console.error('Error submitting form:', error);
            this.showMessage('An error occurred while submitting the form.', 'danger');
        })
        .finally(() => {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.innerHTML = submitButton.getAttribute('data-original-text') || 'Submit';
            }
            
            if (window.spaRouter) {
                window.spaRouter.hideLoading();
            }
        });
    }
    
    /**
     * Show a message to the user
     * @param {string} message - The message to show
     * @param {string} type - The type of message (success, danger, warning, info)
     */
    showMessage(message, type = 'info') {
        let alertContainer = document.querySelector('.alert-container');
        if (!alertContainer) {
            alertContainer = document.createElement('div');
            alertContainer.className = 'alert-container';
            document.body.appendChild(alertContainer);
        }
        
        const alert = document.createElement('div');
        alert.className = `alert alert-${type} alert-dismissible fade show`;
        alert.setAttribute('role', 'alert');
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        alertContainer.appendChild(alert);
        
        setTimeout(() => {
            alert.classList.remove('show');
            setTimeout(() => {
                alert.remove();
            }, 300);
        }, 5000);
    }
    
    /**
     * Show validation errors on a form
     * @param {HTMLFormElement} form - The form with errors
     * @param {Object} errors - The validation errors
     */
    showValidationErrors(form, errors) {
        form.querySelectorAll('.is-invalid').forEach(el => {
            el.classList.remove('is-invalid');
        });
        
        form.querySelectorAll('.invalid-feedback').forEach(el => {
            el.remove();
        });
        
        for (const field in errors) {
            const input = form.querySelector(`[name="${field}"]`);
            if (input) {
                input.classList.add('is-invalid');
                
                const errorDiv = document.createElement('div');
                errorDiv.className = 'invalid-feedback';
                errorDiv.textContent = errors[field];
                
                input.parentNode.insertBefore(errorDiv, input.nextSibling);
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.spaForms = new SPAForms();
});

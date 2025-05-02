/**
 * Main JavaScript for Reverse Proxy Control Center
 */

// Initialize page-specific scripts
function initPageScripts() {
    console.log('Initializing page scripts');
    
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Add fade-out to alerts after 30 seconds (more time to read)
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 30000);
    
    // Automatically focus the first input field on forms
    const firstInput = document.querySelector('form input:not([type="hidden"]):not([readonly]):not([disabled]):first-child');
    if (firstInput) {
        firstInput.focus();
    }
    
    const forms = document.querySelectorAll('form:not(.no-spa)');
    forms.forEach(function(form) {
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            submitButton.setAttribute('data-original-text', submitButton.innerHTML);
        }
        
        form.addEventListener('submit', function(event) {
            console.log('Form is being submitted');
            
            // Check if there's a multiple select with name domain_groups[]
            const domainGroupsSelect = form.querySelector('select[name="domain_groups[]"]');
            if (domainGroupsSelect) {
                console.log('Found domain_groups[] select, selected options:', domainGroupsSelect.selectedOptions.length);
                
                const selectedValues = Array.from(domainGroupsSelect.selectedOptions).map(option => option.value);
                console.log('Selected values:', selectedValues);
            }
        });
    });
    
    // Initialize Socket.IO connections if needed
    initSocketConnections();
}

// Initialize Socket.IO connections
function initSocketConnections() {
    if (typeof io === 'undefined') {
        console.warn('Socket.IO not available');
        return;
    }
    
    const socket = io();
    
    socket.on('connect', function() {
        console.log('Connected to Socket.IO server');
    });
    
    socket.on('disconnect', function() {
        console.log('Disconnected from Socket.IO server');
    });
    
    window.socket = socket;
}

// Initialize scripts when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded');
    initPageScripts();
    
    document.addEventListener('spa:contentUpdated', function() {
        console.log('SPA content updated, reinitializing scripts');
        initPageScripts();
    });
});

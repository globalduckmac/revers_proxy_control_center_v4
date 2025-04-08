document.addEventListener('DOMContentLoaded', function() {
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
    
    // Добавляем обработчик для всех форм на странице
    const forms = document.querySelectorAll('form');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            console.log('Form is being submitted');
            
            // Проверяем, есть ли в форме multiple select с именем domain_groups[]
            const domainGroupsSelect = form.querySelector('select[name="domain_groups[]"]');
            if (domainGroupsSelect) {
                console.log('Found domain_groups[] select, selected options:', domainGroupsSelect.selectedOptions.length);
                
                // Выводим выбранные значения
                const selectedValues = Array.from(domainGroupsSelect.selectedOptions).map(option => option.value);
                console.log('Selected values:', selectedValues);
            }
        });
    });
});

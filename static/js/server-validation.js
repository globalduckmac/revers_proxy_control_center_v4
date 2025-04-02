document.addEventListener('DOMContentLoaded', function() {
    // Get form elements
    const form = document.getElementById('serverForm');
    const authKeyRadio = document.getElementById('auth_key');
    const authPasswordRadio = document.getElementById('auth_password');
    const sshKeySection = document.getElementById('ssh_key_section');
    const sshPasswordSection = document.getElementById('ssh_password_section');
    
    // Function to toggle authentication method sections
    function toggleAuthSections() {
        if (authKeyRadio.checked) {
            sshKeySection.style.display = 'block';
            sshPasswordSection.style.display = 'none';
        } else {
            sshKeySection.style.display = 'none';
            sshPasswordSection.style.display = 'block';
        }
    }
    
    // Add event listeners to radio buttons
    if (authKeyRadio && authPasswordRadio) {
        authKeyRadio.addEventListener('change', toggleAuthSections);
        authPasswordRadio.addEventListener('change', toggleAuthSections);
        
        // Initialize on page load
        toggleAuthSections();
    }
    
    // Form validation
    if (form) {
        form.addEventListener('submit', function(event) {
            let isValid = true;
            
            // Validate IP address
            const ipInput = document.getElementById('ip_address');
            if (ipInput) {
                const ipPattern = /^(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
                
                if (!ipPattern.test(ipInput.value)) {
                    isValid = false;
                    ipInput.classList.add('is-invalid');
                    
                    // Add validation message if it doesn't exist
                    if (!ipInput.nextElementSibling || !ipInput.nextElementSibling.classList.contains('invalid-feedback')) {
                        const feedback = document.createElement('div');
                        feedback.classList.add('invalid-feedback');
                        feedback.innerText = 'Please enter a valid IP address.';
                        ipInput.insertAdjacentElement('afterend', feedback);
                    }
                } else {
                    ipInput.classList.remove('is-invalid');
                }
            }
            
            // Validate authentication method
            if (authKeyRadio.checked) {
                const sshKeyInput = document.getElementById('ssh_key');
                if (sshKeyInput && sshKeyInput.value.trim() === '' && !form.action.includes('edit')) {
                    isValid = false;
                    sshKeyInput.classList.add('is-invalid');
                    
                    if (!sshKeyInput.nextElementSibling || !sshKeyInput.nextElementSibling.classList.contains('invalid-feedback')) {
                        const feedback = document.createElement('div');
                        feedback.classList.add('invalid-feedback');
                        feedback.innerText = 'SSH key is required when using key authentication.';
                        sshKeyInput.insertAdjacentElement('afterend', feedback);
                    }
                } else {
                    sshKeyInput.classList.remove('is-invalid');
                }
            } else {
                const sshPasswordInput = document.getElementById('ssh_password');
                if (sshPasswordInput && sshPasswordInput.value.trim() === '' && !form.action.includes('edit')) {
                    isValid = false;
                    sshPasswordInput.classList.add('is-invalid');
                    
                    if (!sshPasswordInput.nextElementSibling || !sshPasswordInput.nextElementSibling.classList.contains('invalid-feedback')) {
                        const feedback = document.createElement('div');
                        feedback.classList.add('invalid-feedback');
                        feedback.innerText = 'SSH password is required when using password authentication.';
                        sshPasswordInput.insertAdjacentElement('afterend', feedback);
                    }
                } else {
                    sshPasswordInput.classList.remove('is-invalid');
                }
            }
            
            if (!isValid) {
                event.preventDefault();
            }
        });
    }
});

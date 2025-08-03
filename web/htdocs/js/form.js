// Function to save form data to localStorage
function saveFormData() {
    const form = document.getElementById('reachability-form');
    const formData = new FormData(form);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    localStorage.setItem('reachability_form_data', JSON.stringify(data));
}

// Restore form data from localStorage
window.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('reachability-form');
    
    // First check for test mode configuration
    fetch('/cgi-bin/get_test_config.py')
        .then(response => response.json())
        .then(config => {
            console.log('Test config received:', config);
            if (config.mode === 'test' && config.test_ips) {
                // In test mode - check if we have saved data
                const savedData = localStorage.getItem('reachability_form_data');
                
                if (savedData) {
                    // Restore saved data
                    const data = JSON.parse(savedData);
                    // But ensure source and dest IPs match test file
                    data.source_ip = config.test_ips.source || '';
                    data.dest_ip = config.test_ips.destination || '';
                    
                    for (const [key, value] of Object.entries(data)) {
                        const field = form.elements[key];
                        if (field) {
                            field.value = value;
                        }
                    }
                } else {
                    // No saved data - prefill from test config
                    const sourceField = form.elements['source_ip'];
                    const destField = form.elements['dest_ip'];
                    
                    if (sourceField) sourceField.value = config.test_ips.source || '';
                    if (destField) destField.value = config.test_ips.destination || '';
                }
                
                // Always save after setting values
                saveFormData();
            } else {
                // Not in test mode, restore from localStorage
                const savedData = localStorage.getItem('reachability_form_data');
                if (savedData) {
                    const data = JSON.parse(savedData);
                    for (const [key, value] of Object.entries(data)) {
                        const field = form.elements[key];
                        if (field) {
                            field.value = value;
                        }
                    }
                }
            }
        })
        .catch(error => {
            // If fetch fails, fall back to localStorage
            console.error('Failed to fetch test config:', error);
            const savedData = localStorage.getItem('reachability_form_data');
            if (savedData) {
                const data = JSON.parse(savedData);
                for (const [key, value] of Object.entries(data)) {
                    const field = form.elements[key];
                    if (field) {
                        field.value = value;
                    }
                }
            }
        });
    
    // Add event listeners to save form data on input changes
    const inputs = form.querySelectorAll('input, select');
    inputs.forEach(input => {
        input.addEventListener('input', saveFormData);
        input.addEventListener('change', saveFormData);
    });
});

// Save form data before submission
document.getElementById('reachability-form').addEventListener('submit', function(e) {
    saveFormData();
});

// Clear form and localStorage
function clearForm() {
    document.getElementById('reachability-form').reset();
    localStorage.removeItem('reachability_form_data');
    // Reload the page to reinitialize
    location.reload();
}

// Validate IP address format
function validateIP(input) {
    const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
    if (!ipPattern.test(input.value)) {
        input.setCustomValidity('Please enter a valid IP address');
    } else {
        input.setCustomValidity('');
    }
}

// Add IP validation to fields
document.getElementById('source_ip').addEventListener('input', function() {
    validateIP(this);
});

document.getElementById('dest_ip').addEventListener('input', function() {
    validateIP(this);
});
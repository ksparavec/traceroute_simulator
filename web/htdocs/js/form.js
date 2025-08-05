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
    
    // Restore user trace data from sessionStorage if available
    const savedTraceData = sessionStorage.getItem('user_trace_data');
    if (savedTraceData) {
        document.getElementById('user_trace_data').value = savedTraceData;
        console.log('Restored user trace data from sessionStorage');
    }
    
    // Add event listeners to save form data on input changes
    const inputs = form.querySelectorAll('input:not([type="hidden"]), select');
    inputs.forEach(input => {
        input.addEventListener('input', saveFormData);
        input.addEventListener('change', saveFormData);
    });
});

// Removed - combined with the main submit handler below

// Clear form and localStorage - made globally accessible
window.clearForm = function() {
    document.getElementById('reachability-form').reset();
    localStorage.removeItem('reachability_form_data');
    sessionStorage.removeItem('user_trace_data');
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

// Setup validation event listeners after DOM is ready
setTimeout(function() {
    const sourceIp = document.getElementById('source_ip');
    const destIp = document.getElementById('dest_ip');
    
    if (sourceIp) {
        sourceIp.addEventListener('input', function() {
            validateIP(this);
        });
    }
    
    if (destIp) {
        destIp.addEventListener('input', function() {
            validateIP(this);
        });
    }
}, 100);

// Modal functions for trace file input - moved outside DOMContentLoaded to be globally accessible
window.openTraceFileInput = function() {
    console.log('openTraceFileInput called');
    const modal = document.getElementById('traceModal');
    if (!modal) {
        console.error('Modal element not found!');
        return;
    }
    console.log('Setting modal display to block');
    modal.style.display = 'block';
    
    // Load any previously saved trace data
    const savedTrace = sessionStorage.getItem('user_trace_data');
    if (savedTrace) {
        document.getElementById('traceJsonInput').value = savedTrace;
    }
}

window.closeTraceModal = function() {
    const modal = document.getElementById('traceModal');
    modal.style.display = 'none';
}

window.clearTraceInput = function() {
    document.getElementById('traceJsonInput').value = '';
    document.getElementById('jsonValidationError').style.display = 'none';
    sessionStorage.removeItem('user_trace_data');
}

window.validateAndSaveTrace = function() {
    const traceInput = document.getElementById('traceJsonInput').value.trim();
    const errorDiv = document.getElementById('jsonValidationError');
    
    if (!traceInput) {
        errorDiv.textContent = 'Please provide JSON trace data';
        errorDiv.style.display = 'block';
        return;
    }
    
    try {
        // Validate JSON format
        const jsonData = JSON.parse(traceInput);
        
        // Store in hidden form field
        document.getElementById('user_trace_data').value = traceInput;
        
        // Also store in sessionStorage for persistence
        sessionStorage.setItem('user_trace_data', traceInput);
        
        // Hide error message
        errorDiv.style.display = 'none';
        
        // Close modal
        closeTraceModal();
        
        // Show success feedback
        alert('Trace file loaded successfully. It will be used when you run the test.');
        
    } catch (e) {
        errorDiv.textContent = 'Invalid JSON format: ' + e.message;
        errorDiv.style.display = 'block';
    }
}

// Close modal when clicking outside of it
window.addEventListener('click', function(event) {
    const modal = document.getElementById('traceModal');
    if (event.target === modal) {
        closeTraceModal();
    }
});

// Handle form submission - restore user trace data to hidden field
document.getElementById('reachability-form').addEventListener('submit', function(e) {
    // Save form data
    saveFormData();
    
    // Get user trace data from sessionStorage and put it in hidden field
    const userTraceData = sessionStorage.getItem('user_trace_data');
    if (userTraceData) {
        console.log('Restoring user trace data to hidden field, length:', userTraceData.length);
        document.getElementById('user_trace_data').value = userTraceData;
    } else {
        console.log('No user trace data found in sessionStorage');
    }
    
    // Let the form submit normally (no preventDefault)
});
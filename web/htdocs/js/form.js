// Restore form data from localStorage
window.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('reachability-form');
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

// Save form data before submission
document.getElementById('reachability-form').addEventListener('submit', function(e) {
    const formData = new FormData(this);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    localStorage.setItem('reachability_form_data', JSON.stringify(data));
});

// Clear form and localStorage
function clearForm() {
    document.getElementById('reachability-form').reset();
    localStorage.removeItem('reachability_form_data');
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
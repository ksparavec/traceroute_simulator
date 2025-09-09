// Load quick select services from config
function loadQuickSelectServices() {
    fetch('/services-config')
        .then(response => response.json())
        .then(data => {
            const quickPorts = document.getElementById('quick_ports');
            if (quickPorts && data.services) {
                // Clear existing options
                quickPorts.innerHTML = '';
                
                // Add options from config
                data.services.forEach(service => {
                    const option = document.createElement('option');
                    option.value = `${service.port}/${service.protocol}`;
                    option.text = `${service.name} (${service.port}/${service.protocol}) - ${service.description}`;
                    quickPorts.appendChild(option);
                });
                
                // After loading services, restore saved selections
                restoreSavedSelections();
            }
        })
        .catch(error => {
            console.error('Failed to load services config:', error);
            // Fall back to some default services
            const quickPorts = document.getElementById('quick_ports');
            if (quickPorts) {
                const defaults = [
                    {value: '22/tcp', text: 'SSH (22/tcp) - Secure Shell'},
                    {value: '80/tcp', text: 'HTTP (80/tcp) - Web Traffic'},
                    {value: '443/tcp', text: 'HTTPS (443/tcp) - Secure Web'},
                    {value: '3389/tcp', text: 'RDP (3389/tcp) - Remote Desktop'}
                ];
                defaults.forEach(service => {
                    const option = document.createElement('option');
                    option.value = service.value;
                    option.text = service.text;
                    quickPorts.appendChild(option);
                });
                restoreSavedSelections();
            }
        });
}

// Function to restore saved quick port selections
function restoreSavedSelections() {
    const savedData = localStorage.getItem('reachability_form_data');
    if (savedData) {
        const data = JSON.parse(savedData);
        if (data.quick_ports) {
            const quickPorts = document.getElementById('quick_ports');
            const selectedValues = Array.isArray(data.quick_ports) ? data.quick_ports : [];
            if (quickPorts) {
                for (let option of quickPorts.options) {
                    option.selected = selectedValues.includes(option.value);
                }
            }
        }
    }
}

// Function to save form data to localStorage
function saveFormData() {
    const form = document.getElementById('reachability-form');
    const formData = new FormData(form);
    const data = {};
    
    for (const [key, value] of formData.entries()) {
        // Skip quick_ports as we'll handle it separately
        if (key !== 'quick_ports') {
            data[key] = value;
        }
    }
    
    // Handle multi-select quick_ports specially
    const quickPorts = document.getElementById('quick_ports');
    const selectedPorts = [];
    for (let option of quickPorts.options) {
        if (option.selected) {
            selectedPorts.push(option.value);
        }
    }
    data.quick_ports = selectedPorts;
    
    // Explicitly save the port mode radio button value
    const portModeRadio = document.querySelector('input[name="port_mode"]:checked');
    if (portModeRadio) {
        data.port_mode = portModeRadio.value;
    }
    
    localStorage.setItem('reachability_form_data', JSON.stringify(data));
}

// Restore form data from localStorage
window.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('reachability-form');
    
    // Load quick select services first
    loadQuickSelectServices();
    
    // First check for test mode configuration
    fetch('/test-config')
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
                            // Handle different field types
                            if (key === 'quick_ports') {
                                // Skip - will be handled by restoreSavedSelections() after services are loaded
                            } else if (field.type === 'radio-button' || (field[0] && field[0].type === 'radio')) {
                                // Handle radio buttons
                                const radios = form.querySelectorAll(`input[name="${key}"]`);
                                radios.forEach(radio => {
                                    radio.checked = (radio.value === value);
                                });
                            } else {
                                field.value = value;
                            }
                        }
                    }
                    
                    // Ensure port group visibility is already set above
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
                    // FIRST: Set the visibility of port groups based on saved mode
                    const portMode = data.port_mode || 'quick';
                    if (portMode === 'manual') {
                        document.getElementById('quick_select_group').style.display = 'none';
                        document.getElementById('manual_entry_group').style.display = 'block';
                    } else {
                        document.getElementById('quick_select_group').style.display = 'block';
                        document.getElementById('manual_entry_group').style.display = 'none';
                    }
                    
                    // THEN: Restore all form values
                    for (const [key, value] of Object.entries(data)) {
                        const field = form.elements[key];
                        if (field) {
                            // Handle different field types
                            if (key === 'quick_ports') {
                                // Skip - will be handled by restoreSavedSelections() after services are loaded
                            } else if (field.type === 'radio-button' || (field[0] && field[0].type === 'radio')) {
                                // Handle radio buttons
                                const radios = form.querySelectorAll(`input[name="${key}"]`);
                                radios.forEach(radio => {
                                    radio.checked = (radio.value === value);
                                });
                            } else if (field) {
                                field.value = value;
                            }
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
                        // Handle different field types
                        if (key === 'quick_ports') {
                            // Skip - will be handled by restoreSavedSelections() after services are loaded
                        } else if (field.type === 'radio-button' || (field[0] && field[0].type === 'radio')) {
                            // Handle radio buttons
                            const radios = form.querySelectorAll(`input[name="${key}"]`);
                            radios.forEach(radio => {
                                radio.checked = (radio.value === value);
                            });
                        } else {
                            field.value = value;
                        }
                    }
                }
                
                // After restoring, make sure the correct port input group is visible
                const portMode = data.port_mode || 'quick';
                if (portMode === 'manual') {
                    document.getElementById('quick_select_group').style.display = 'none';
                    document.getElementById('manual_entry_group').style.display = 'block';
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

// Toggle between quick select and manual entry modes
window.togglePortMode = function() {
    const portMode = document.querySelector('input[name="port_mode"]:checked').value;
    const quickGroup = document.getElementById('quick_select_group');
    const manualGroup = document.getElementById('manual_entry_group');
    const destPorts = document.getElementById('dest_ports');
    const quickPorts = document.getElementById('quick_ports');
    
    if (portMode === 'quick') {
        quickGroup.style.display = 'block';
        manualGroup.style.display = 'none';
        // Clear manual entry and remove any validation
        destPorts.value = '';
        destPorts.setCustomValidity('');
    } else {
        quickGroup.style.display = 'none';
        manualGroup.style.display = 'block';
        // Clear quick select
        for (let option of quickPorts.options) {
            option.selected = false;
        }
    }
}

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

// Function to count services from port specification
function countServicesFromPortSpec(portSpec, defaultProtocol) {
    let totalServices = 0;
    const parts = portSpec.split(',').map(p => p.trim()).filter(p => p);
    
    for (const part of parts) {
        // Check if it's a range
        const rangeParts = part.split('-');
        if (rangeParts.length === 2) {
            // It's a range
            let startPort, endPort;
            
            // Handle protocol in first part of range
            const firstPart = rangeParts[0].trim();
            const firstPortMatch = firstPart.match(/^(\d+)/);
            if (firstPortMatch) {
                startPort = parseInt(firstPortMatch[1]);
            } else {
                continue; // Invalid format
            }
            
            // Handle second part of range (might have protocol)
            const secondPart = rangeParts[1].trim();
            const secondPortMatch = secondPart.match(/^(\d+)/);
            if (secondPortMatch) {
                endPort = parseInt(secondPortMatch[1]);
            } else {
                continue; // Invalid format
            }
            
            if (startPort && endPort && startPort <= endPort) {
                // Count each port in the range
                totalServices += (endPort - startPort + 1);
            }
        } else {
            // Single port (might have multiple protocols)
            const portProto = part.split('/')[0].trim();
            if (portProto && !isNaN(parseInt(portProto))) {
                totalServices += 1;
            }
        }
    }
    
    return totalServices;
}

// Handle form submission - restore user trace data to hidden field
document.getElementById('reachability-form').addEventListener('submit', function(e) {
    // First validate the number of services
    const portMode = document.querySelector('input[name="port_mode"]:checked').value;
    let serviceCount = 0;
    
    if (portMode === 'quick') {
        // Count selected services in quick mode
        const quickPorts = document.getElementById('quick_ports');
        serviceCount = quickPorts.selectedOptions.length;
    } else {
        // Count services from manual entry (including ranges)
        const destPorts = document.getElementById('dest_ports').value.trim();
        const defaultProtocol = document.getElementById('default_protocol').value;
        if (destPorts) {
            serviceCount = countServicesFromPortSpec(destPorts, defaultProtocol);
        }
    }
    
    // Check if service count exceeds limit
    if (serviceCount > 10) {
        e.preventDefault(); // Stop form submission
        
        // Show error message
        alert(`Too many services selected (${serviceCount} services).\n\n` +
              `Please reduce the number of services to 10 or less.\n` +
              `Note: Each port in a range counts as a separate service.\n\n` +
              `Current selection: ${serviceCount} services`);
        return;
    }
    
    if (serviceCount === 0) {
        e.preventDefault(); // Stop form submission
        alert('Please select at least one service to test.');
        return;
    }
    
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
// TSIM Reachability Form JS (clean version)
// TSIM_MODE is now injected server-side via window.TSIM_MODE
// Default to 'prod' if not set for some reason
if (typeof window.TSIM_MODE === 'undefined') {
    window.TSIM_MODE = 'prod';
}

// Validate destination port specification tokens
function isValidDestSpec(spec) {
    if (!spec) return false;
    const tokens = spec.split(',').map(p => p.trim()).filter(Boolean);
    if (tokens.length === 0) return false;
    const re = /^(\d+)(?:-(\d+))?(?:\/(tcp|udp))?$/i;
    for (const t of tokens) {
        if (!re.test(t)) return false;
        const m = t.match(/^(\d+)(?:-(\d+))?/);
        if (m && m[1] && m[2] && parseInt(m[1]) > parseInt(m[2])) return false; // invalid range
    }
    return true;
}

function loadQuickSelectServices() {
    fetch('/services-config')
        .then(r => r.json())
        .then(data => {
            const quickPorts = document.getElementById('quick_ports');
            if (!quickPorts) return;
            quickPorts.innerHTML = '';
            const services = (data && data.services) || [];
            services.forEach(s => {
                const opt = document.createElement('option');
                // Set value based on format
                if (s.ports) {
                    opt.value = s.ports;
                } else if (s.port && s.protocol) {
                    opt.value = `${s.port}/${s.protocol}`;
                } else {
                    // Skip invalid service
                    return;
                }
                
                // Set display text - prefer display field if available
                if (s.display) {
                    opt.text = s.display;
                } else if (s.ports) {
                    opt.text = `${s.name} - ${s.description}`;
                } else {
                    opt.text = `${s.name} (${s.port}/${s.protocol}) - ${s.description}`;
                }
                
                quickPorts.appendChild(opt);
            });
            restoreSavedSelections();
        })
        .catch(() => {
            const quickPorts = document.getElementById('quick_ports');
            if (!quickPorts) return;
            const defaults = [
                {value: '22/tcp', text: 'SSH (22/tcp) - Secure Shell'},
                {value: '80/tcp', text: 'HTTP (80/tcp) - Web Traffic'},
                {value: '443/tcp', text: 'HTTPS (443/tcp) - Secure Web'},
                {value: '3389/tcp', text: 'RDP (3389/tcp) - Remote Desktop'}
            ];
            defaults.forEach(d => {
                const opt = document.createElement('option');
                opt.value = d.value;
                opt.text = d.text;
                quickPorts.appendChild(opt);
            });
            restoreSavedSelections();
        });
}

function restoreSavedSelections() {
    const saved = localStorage.getItem('reachability_form_data');
    if (!saved) return;
    const data = JSON.parse(saved);
    const quickPorts = document.getElementById('quick_ports');
    if (!quickPorts || !Array.isArray(data.quick_ports)) return;
    for (let opt of quickPorts.options) {
        opt.selected = data.quick_ports.includes(opt.value);
    }
}

function saveFormData() {
    const form = document.getElementById('reachability-form');
    const fd = new FormData(form);
    const data = {};
    for (const [k, v] of fd.entries()) {
        if (k !== 'quick_ports') data[k] = v;
    }
    const quickPorts = document.getElementById('quick_ports');
    const selected = [];
    for (let opt of quickPorts.options) if (opt.selected) selected.push(opt.value);
    data.quick_ports = selected;
    const pm = document.querySelector('input[name="port_mode"]:checked');
    if (pm) data.port_mode = pm.value;
    localStorage.setItem('reachability_form_data', JSON.stringify(data));
}

function setVisible(el, yes) {
    if (!el) return;
    const grp = el.closest('.form-group');
    if (grp) grp.style.display = yes ? 'block' : 'none';
}

function setDisabled(el, yes) {
    if (!el) return;
    el.disabled = !!yes;
    if (yes) el.removeAttribute('required');
}

window.togglePortMode = function() {
    const mode = document.querySelector('input[name="port_mode"]:checked')?.value || 'quick';
    setVisible(document.getElementById('quick_select_group'), mode !== 'manual');
    setVisible(document.getElementById('manual_entry_group'), mode === 'manual');
};

window.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('reachability-form');
    const src = document.getElementById('source_ip');
    const srcPort = document.getElementById('source_port');
    const dst = document.getElementById('dest_ip');
    const traceBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Trace File Input'));
    const userTraceHidden = document.getElementById('user_trace_data');

    loadQuickSelectServices();

    // Apply mode-specific UI immediately (no fetch needed - mode is already set)
    // Toggle body class for mode-specific styling
    document.body.classList.toggle('tsim-mode-prod', window.TSIM_MODE === 'prod');
    document.body.classList.toggle('tsim-mode-test', window.TSIM_MODE === 'test');
    // Update page titles based on mode
    const modeTitle = window.TSIM_MODE === 'test'
        ? 'Network Reachability Test (Mode: Testing)'
        : 'Network Reachability Test (Mode: Production)';
    document.title = modeTitle;
    const h1 = document.querySelector('header h1');
    if (h1) h1.textContent = modeTitle;
    if (window.TSIM_MODE === 'test') {
        // Hide and disable IP inputs; show trace upload
        setVisible(src, false); setDisabled(src, true);
        setVisible(srcPort, true); setDisabled(srcPort, false);
        setVisible(dst, false); setDisabled(dst, true);
        if (traceBtn) {
            traceBtn.style.display = 'inline-block';
            // Move Trace button to the top of the form in test mode
            const firstGroup = form.querySelector('.form-group');
            if (firstGroup && traceBtn.parentElement) {
                // Create or reuse a top container
                let topContainer = document.getElementById('trace_top_container');
                if (!topContainer) {
                    topContainer = document.createElement('div');
                    topContainer.id = 'trace_top_container';
                    topContainer.className = 'form-group';
                }
                // Place the button into the top container
                topContainer.innerHTML = '';
                const hint = document.createElement('div');
                hint.className = 'help-text';
                hint.textContent = 'Paste a JSON formatted trace file via the button above';
                // Center button and help text in test mode
                topContainer.style.textAlign = 'center';
                traceBtn.style.display = 'inline-block';
                traceBtn.style.margin = '8px auto';
                hint.style.textAlign = 'center';
                // Append elements
                topContainer.appendChild(traceBtn);
                topContainer.appendChild(hint);
                form.insertBefore(topContainer, firstGroup);
            }
        }
    } else {
        setVisible(src, true); setDisabled(src, false);
        setVisible(srcPort, true); setDisabled(srcPort, false);
        setVisible(dst, true); setDisabled(dst, false);
        if (traceBtn) traceBtn.style.display = 'none';
        // Ensure no leftover trace data is submitted in prod
        localStorage.removeItem('user_trace_data');
        if (userTraceHidden) userTraceHidden.value = '';
    }

    // Restore saved form values (except hidden/disabled ones in test mode)
    const saved = localStorage.getItem('reachability_form_data');
    if (saved) {
        const data = JSON.parse(saved);
        Object.entries(data).forEach(([k, v]) => {
            const field = form.elements[k];
            if (!field) return;
            if (k === 'quick_ports') return; // handled elsewhere
            if (field[0] && field[0].type === 'radio') {
                form.querySelectorAll(`input[name="${k}"]`).forEach(r => r.checked = (r.value === v));
            } else if (!field.disabled) {
                field.value = v;
            }
        });
        window.togglePortMode();
    }

    // Restore user trace data in test mode
    if (window.TSIM_MODE === 'test') {
        const savedTrace = localStorage.getItem('user_trace_data');
        if (savedTrace && userTraceHidden) userTraceHidden.value = savedTrace;
    }

    // Show Queue Admin link for admin users
    fetch('/login')
        .then(r => r.json())
        .then(info => {
            if (info && info.logged_in && (info.role === 'admin' || info.role === 'administrator')) {
                const link = document.getElementById('queueAdminLink');
                if (link) link.style.display = 'inline-block';
            }
        })
        .catch(() => {});

    // Input listeners
    form.querySelectorAll('input:not([type="hidden"]), select').forEach(inp => {
        inp.addEventListener('input', saveFormData);
        inp.addEventListener('change', saveFormData);
    });

    // Submit validation (via AJAX to handle server-side errors gracefully)
    form.addEventListener('submit', async (e) => {
        // Service count limit 10
        const pm = document.querySelector('input[name="port_mode"]:checked')?.value || 'quick';
        // Manual mode: validate dest_ports format early and show detailed hint
        if (pm === 'manual') {
            const destEl = document.getElementById('dest_ports');
            const spec = (destEl?.value || '').trim();
            if (!isValidDestSpec(spec)) {
                e.preventDefault();
                const hintEl = destEl?.closest('.form-group')?.querySelector('.help-text');
                const hint = hintEl ? hintEl.innerText : 'Format: port[/protocol], port-range[/protocol], comma-separated. Examples: 22/tcp, 80, 443/tcp, 1000-2000/udp, 53/tcp,53/udp';
                showError(hint);
                return;
            }
        }
        let count = 0;
        if (pm === 'quick') {
            count = document.getElementById('quick_ports').selectedOptions.length;
        } else {
            const spec = document.getElementById('dest_ports').value.trim();
            const parts = spec.split(',').map(p => p.trim()).filter(Boolean);
            for (const part of parts) {
                const m = part.match(/^(\d+)(?:-(\d+))?/);
                if (!m) continue;
                if (m[2]) count += (parseInt(m[2]) - parseInt(m[1]) + 1); else count += 1;
            }
        }
        if (count === 0) {
            e.preventDefault();
            showError('Please select at least one destination service to test.');
            return;
        }
        if (count > 10) {
            e.preventDefault();
            showError(`Too many services selected (${count}). Max is 10.`);
            return;
        }

        // Enforce mode-specific requirements
        if (TSIM_MODE === 'test') {
            const traceData = localStorage.getItem('user_trace_data') || '';
            if (!traceData.trim()) {
                e.preventDefault();
                showError('Trace File Input is required in test mode.');
                return;
            }
            if (userTraceHidden) userTraceHidden.value = traceData;
        } else {
            // Ensure hidden field is empty in prod
            if (userTraceHidden) userTraceHidden.value = '';
        }
        // Perform AJAX submission to capture server-side validation errors
        e.preventDefault();
        saveFormData();
        try {
            const fd = new FormData(form);
            const resp = await fetch('/main', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                body: fd
            });
            const ct = resp.headers.get('content-type') || '';
            let payload = null;
            if (ct.includes('application/json')) {
                payload = await resp.json();
            } else {
                payload = await resp.text();
            }
            if (!resp.ok) {
                const msg = (payload && payload.message) || (payload && payload.error) || 'Request failed. Please check your inputs and try again.';
                showError(msg);
                return;
            }
            if (payload && payload.success) {
                const url = (payload.redirect) || `/progress.html?id=${payload.run_id}`;
                window.location.href = url;
            } else {
                const msg = (payload && (payload.message || payload.error)) || 'Unexpected response. Please try again.';
                showError(msg);
            }
        } catch (err) {
            showError('Network or server error. Please try again.');
        }
    });
});

// Modal functions for trace file input
window.openTraceFileInput = function() {
    const modal = document.getElementById('traceModal');
    if (modal) {
        const saved = localStorage.getItem('user_trace_data');
        if (saved) document.getElementById('traceJsonInput').value = saved;
        modal.style.display = 'block';
    }
};

window.closeTraceModal = function() {
    const modal = document.getElementById('traceModal');
    if (modal) modal.style.display = 'none';
};

window.clearTraceInput = function() {
    const ta = document.getElementById('traceJsonInput');
    const err = document.getElementById('jsonValidationError');
    if (ta) ta.value = '';
    if (err) err.style.display = 'none';
    localStorage.removeItem('user_trace_data');
    const hidden = document.getElementById('user_trace_data');
    if (hidden) hidden.value = '';
};

window.validateAndSaveTrace = function() {
    const ta = document.getElementById('traceJsonInput');
    const err = document.getElementById('jsonValidationError');
    const val = (ta?.value || '').trim();
    if (!val) {
        if (err) { err.textContent = 'Please provide JSON trace data'; err.style.display = 'block'; }
        return;
    }
    try {
        JSON.parse(val);
        localStorage.setItem('user_trace_data', val);
        const hidden = document.getElementById('user_trace_data');
        if (hidden) hidden.value = val;
        if (err) err.style.display = 'none';
        window.closeTraceModal();
        alert('Trace file loaded successfully. It will be used when you run the test.');
    } catch (e) {
        if (err) { err.textContent = 'Invalid JSON format: ' + e.message; err.style.display = 'block'; }
    }
};

// Error modal helpers
function showError(message) {
    const modal = document.getElementById('errorModal');
    const box = document.getElementById('errorModalMessage');
    if (box) box.textContent = message || 'An error occurred.';
    if (modal) modal.style.display = 'block';
}

window.closeErrorModal = function() {
    const modal = document.getElementById('errorModal');
    if (modal) modal.style.display = 'none';
};

// Clear all selections and inputs (both modes)
window.clearForm = function() {
    const form = document.getElementById('reachability-form');
    if (!form) return;
    // Text inputs
    const ids = ['source_ip', 'source_port', 'dest_ip', 'dest_ports'];
    ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    // Multi-select
    const quick = document.getElementById('quick_ports');
    if (quick) { Array.from(quick.options).forEach(o => o.selected = false); }
    // Radio defaults
    const pmQuick = form.querySelector('input[name="port_mode"][value="quick"]');
    if (pmQuick) pmQuick.checked = true;
    // Default protocol
    const proto = document.getElementById('default_protocol');
    if (proto) proto.value = 'tcp';
    // Hidden trace field and stored data
    const hidden = document.getElementById('user_trace_data');
    if (hidden) hidden.value = '';
    sessionStorage.removeItem('user_trace_data');
    const ta = document.getElementById('traceJsonInput');
    if (ta) ta.value = '';
    const err = document.getElementById('jsonValidationError');
    if (err) err.style.display = 'none';
    // Persist cleared state and update visibility sections
    localStorage.removeItem('reachability_form_data');
    window.togglePortMode();
};

// Close modal when clicking outside of it
window.addEventListener('click', function(event) {
    const modal = document.getElementById('traceModal');
    if (event.target === modal) {
        window.closeTraceModal();
    }
});

# Frontend Migration Guide for WSGI

This document outlines all the frontend JavaScript and HTML changes required to complete the migration from CGI to WSGI.

## URL Endpoint Mapping

All frontend files need to be updated to use the new WSGI API endpoints:

| Old CGI Endpoint | New WSGI Endpoint | 
|-----------------|-------------------|
| `/cgi-bin/login.py` | `/api/login` |
| `/cgi-bin/logout.py` | `/api/logout` |
| `/cgi-bin/main.py` | `/api/main` |
| `/cgi-bin/pdf_viewer.py` | `/api/pdf` |
| `/cgi-bin/get_progress.py` | `/api/progress` |
| `/cgi-bin/progress_stream.py` | `/api/progress-stream` |
| `/cgi-bin/get_services_config.py` | `/api/services-config` |
| `/cgi-bin/get_test_config.py` | `/api/test-config` |
| `/cgi-bin/cleanup.py` | `/api/cleanup` |

## Files That Need Updates

### 1. **login.html**
```javascript
// OLD
fetch('/cgi-bin/login.py', {
    method: 'POST',
    body: formData
})

// NEW
fetch('/api/login', {
    method: 'POST',
    body: formData
})
```

### 2. **form.html** (Main test form)
```javascript
// OLD
fetch('/cgi-bin/main.py', {
    method: 'POST',
    body: formData
})

// NEW
fetch('/api/main', {
    method: 'POST',
    body: formData
})

// Also update services config fetch:
// OLD
fetch('/cgi-bin/get_services_config.py')

// NEW
fetch('/api/services-config')

// And test config fetch:
// OLD
fetch('/cgi-bin/get_test_config.py')

// NEW
fetch('/api/test-config')
```

### 3. **progress.html**
```javascript
// OLD
fetch('/cgi-bin/get_progress.py?run_id=' + runId)

// NEW
fetch('/api/progress?run_id=' + runId)

// For Server-Sent Events:
// OLD
const eventSource = new EventSource('/cgi-bin/progress_stream.py?run_id=' + runId + '&session=' + sessionId)

// NEW
const eventSource = new EventSource('/api/progress-stream?run_id=' + runId + '&session=' + sessionId)
```

### 4. **pdf_viewer_final.html**
```javascript
// OLD
fetch('/cgi-bin/pdf_viewer.py?id=' + runId)

// NEW
fetch('/api/pdf?id=' + runId)
```

### 5. **All pages with logout functionality**
```javascript
// OLD
window.location.href = '/cgi-bin/logout.py'

// NEW
window.location.href = '/api/logout'
```

### 6. **admin.html** (if exists)
```javascript
// OLD
fetch('/cgi-bin/cleanup.py', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({action: 'cleanup'})
})

// NEW
fetch('/api/cleanup', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({action: 'cleanup'})
})
```

## Global Configuration Approach

To make the migration easier and allow for easy rollback, you can use a global configuration variable in each HTML file:

```javascript
// Add this at the top of each JavaScript section
const API_BASE = '/api';  // Change to '/cgi-bin' to rollback

// Then use throughout the code:
fetch(`${API_BASE}/login`, { ... })
fetch(`${API_BASE}/main`, { ... })
fetch(`${API_BASE}/progress`, { ... })
```

## Testing Checklist

After updating the frontend files, test the following workflows:

- [ ] **Authentication Flow**
  - [ ] Login page submits to `/api/login`
  - [ ] Successful login redirects properly
  - [ ] Logout works from all pages

- [ ] **Main Test Execution**
  - [ ] Form submission to `/api/main`
  - [ ] Service configuration loaded from `/api/services-config`
  - [ ] Test configuration loaded from `/api/test-config`
  - [ ] Progress updates via `/api/progress`
  - [ ] Real-time progress via SSE at `/api/progress-stream`

- [ ] **Results Viewing**
  - [ ] PDF viewer loads from `/api/pdf`
  - [ ] Download links work correctly

- [ ] **Admin Functions**
  - [ ] Cleanup endpoint at `/api/cleanup` (if admin panel exists)

## Backward Compatibility

The Apache configuration includes rewrite rules that redirect old CGI URLs to new WSGI endpoints, so the application will continue to work during the migration. However, updating the frontend is recommended for better performance (avoids unnecessary redirects).

## Deployment Steps

1. **Test in Development**
   - Update one HTML file at a time
   - Test each function thoroughly
   - Use browser developer tools to verify correct API calls

2. **Stage Deployment**
   - Deploy updated frontend files to staging server
   - Test with real WSGI backend
   - Verify all workflows

3. **Production Deployment**
   - Deploy during low-traffic period
   - Monitor logs for any errors
   - Keep old CGI files as backup for quick rollback

## Rollback Plan

If issues occur after deployment:

1. **Quick Rollback (with redirects)**
   - Apache redirects ensure old URLs still work
   - No immediate action needed

2. **Full Rollback**
   - Restore original HTML/JS files
   - Disable WSGI site: `sudo a2dissite tsim-wsgi`
   - Enable CGI site: `sudo a2ensite tsim-cgi`
   - Reload Apache: `sudo systemctl reload apache2`

## Notes

- The WSGI implementation returns JSON responses, same as CGI
- Session cookies remain compatible
- File upload handling remains the same (multipart/form-data)
- All API endpoints support both GET and POST methods where appropriate
// Set page title and header by mode across pages
document.addEventListener('DOMContentLoaded', () => {
  try {
    // Fetch configuration first for mode
    fetch('/services-config').then(r => r.json()).catch(() => ({ mode: 'prod' }))
      .then(cfg => {
        const mode = (cfg && cfg.mode) || 'prod';
        const modeText = mode === 'test' ? 'Testing' : 'Production';

        // Update mode display (available on all pages including login)
        const modeDisplay = document.getElementById('modeDisplay');
        if (modeDisplay) {
          modeDisplay.textContent = modeText;
        }

        // Only fetch session info if not on login page
        if (!window.location.pathname.includes('login')) {
          return fetch('/login').then(r => r.json()).catch(() => null);
        }
        return null;
      })
      .then(sessionInfo => {
        // Update user information if available and logged in
        if (sessionInfo && sessionInfo.logged_in) {
          const usernameDisplay = document.getElementById('usernameDisplay');
          const authMethodDisplay = document.getElementById('authMethodDisplay');
          const loginTimestampDisplay = document.getElementById('loginTimestampDisplay');

          if (usernameDisplay) {
            usernameDisplay.textContent = sessionInfo.username || 'Unknown';
          }
          if (authMethodDisplay) {
            const authMethod = sessionInfo.auth_method || 'local';
            authMethodDisplay.textContent = authMethod === 'pam' ? 'PAM' : 'Local';
          }
          if (loginTimestampDisplay) {
            loginTimestampDisplay.textContent = sessionInfo.login_timestamp || 'Unknown';
          }

          // Show admin link if user has admin role
          if (sessionInfo.role === 'admin') {
            const adminLink = document.getElementById('queueAdminLink');
            if (adminLink) {
              adminLink.style.display = 'inline-block';
            }
          }
        }

        // Update document title - now using new title
        document.title = 'Network Service Reachability Analyzer';

        // Update h1 headers if they don't have the user info section
        const headerH1 = document.querySelector('header h1');
        const loginH1 = document.querySelector('.login-container h1');
        const pdfH = document.querySelector('.pdf-header h3');

        // Only update PDF h3, others are already updated in HTML
        if (pdfH) pdfH.textContent = 'Network Service Reachability Analyzer';
      });
  } catch (_) { /* ignore */ }
});


// Set page title and header by mode across pages
document.addEventListener('DOMContentLoaded', () => {
  try {
    fetch('/services-config')
      .then(r => r.json())
      .then(cfg => {
        const mode = (cfg && cfg.mode) || 'prod';
        const title = mode === 'test'
          ? 'Network Reachability Test (Mode: Testing)'
          : 'Network Reachability Test (Mode: Production)';

        // Document title
        document.title = title;

        // Common header locations
        const headerH1 = document.querySelector('header h1');
        const loginH1 = document.querySelector('.login-container h1');
        const pdfH = document.querySelector('.pdf-header h3');

        if (headerH1) headerH1.textContent = title;
        if (loginH1) loginH1.textContent = title;
        if (pdfH) pdfH.textContent = title;
      })
      .catch(() => { /* ignore */ });
  } catch (_) { /* ignore */ }
});


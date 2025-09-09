# TSIM WSGI Deployment Guide

## Overview

This directory contains the WSGI (Web Server Gateway Interface) implementation of the TSIM Traceroute Simulator web application. This implementation replaces the legacy CGI-based system with a modern, high-performance WSGI architecture.

## Key Features

- **Persistent Python processes** - Eliminates CGI overhead
- **Complete module preloading** - All modules loaded at startup for maximum performance
- **RAM-based storage** - All temporary files in /dev/shm/tsim for ultra-fast I/O
- **Direct Python imports** - Scripts imported as libraries instead of subprocess calls
- **Server-Sent Events (SSE)** - Real-time progress streaming
- **Improved security** - Centralized authentication and validation

## Directory Structure

```
wsgi/
├── app.wsgi              # WSGI entry point with module preloading
├── tsim_app.py           # Main application router
├── config.json           # Configuration file
├── apache-site.conf.template  # Apache configuration template
├── handlers/             # Request handlers (10 modules)
│   ├── tsim_base_handler.py
│   ├── tsim_login_handler.py
│   ├── tsim_logout_handler.py
│   ├── tsim_main_handler.py
│   ├── tsim_pdf_handler.py
│   ├── tsim_progress_handler.py
│   ├── tsim_progress_stream_handler.py
│   ├── tsim_services_config_handler.py
│   ├── tsim_test_config_handler.py
│   └── tsim_cleanup_handler.py
├── services/             # Core services
│   ├── tsim_config_service.py
│   ├── tsim_session_manager.py
│   ├── tsim_logger_service.py
│   ├── tsim_auth_service.py
│   ├── tsim_validator_service.py
│   ├── tsim_port_parser_service.py
│   ├── tsim_timing_service.py
│   ├── tsim_lock_manager_service.py
│   ├── tsim_executor.py
│   ├── tsim_hybrid_executor.py
│   └── tsim_performance_middleware.py
├── scripts/              # Refactored scripts (library + CLI)
│   ├── tsim_reachability_tester.py
│   ├── tsim_reachability_visualizer.py
│   └── tsim_packet_analyzer.py
└── htdocs/               # Static web files
    ├── index.html
    ├── login.html
    ├── form.html
    ├── progress.html
    ├── pdf_viewer_final.html
    ├── css/
    │   └── style.css
    └── js/
        ├── api.js        # Centralized API configuration
        └── form.js

```

## Installation

### 1. Prerequisites

```bash
# Install Apache with mod_wsgi
sudo apt-get install apache2 libapache2-mod-wsgi-py3

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure Apache

1. Copy and customize the Apache configuration template:
```bash
sudo cp apache-site.conf.template /etc/apache2/sites-available/tsim.conf
```

2. Edit `/etc/apache2/sites-available/tsim.conf`:
   - Replace `{{SERVER_NAME}}` with your domain/hostname
   - Replace `{{DOCUMENT_ROOT}}` with your document root path
   - Replace `{{WSGI_PATH}}` with the full path to this wsgi directory
   - Replace `{{PYTHON_PATH}}` with your Python environment path (if using venv)

3. Enable the site and required modules:
```bash
sudo a2enmod wsgi headers deflate
sudo a2ensite tsim
sudo a2dissite 000-default  # Optional: disable default site
sudo systemctl reload apache2
```

### 3. Configure the Application

Edit `config.json` to match your environment:

```json
{
    "raw_facts_dir": "/path/to/raw_facts",
    "data_dir": "/dev/shm/tsim/data",
    "session_dir": "/dev/shm/tsim/sessions",
    "run_dir": "/dev/shm/tsim/runs",
    "scripts_dir": "/dev/shm/tsim/scripts",
    "lock_dir": "/dev/shm/tsim/locks",
    "matplotlib_cache": "/dev/shm/tsim/matplotlib_cache",
    "log_dir": "/var/log/tsim",
    "auth": {
        "users": {
            "admin": "hashed_password_here"
        }
    }
}
```

### 4. Create Required Directories

```bash
# Create all directories in RAM (except logs)
sudo mkdir -p /dev/shm/tsim/{sessions,runs,data,scripts,locks,temp,matplotlib_cache}
sudo chown www-data:www-data /dev/shm/tsim -R

# Create log directory (persistent storage)
sudo mkdir -p /var/log/tsim
sudo chown www-data:www-data /var/log/tsim
```

### 5. Set Permissions

```bash
# Set ownership for WSGI files
sudo chown -R www-data:www-data /path/to/wsgi

# Set appropriate permissions
find /path/to/wsgi -type d -exec chmod 755 {} \;
find /path/to/wsgi -type f -exec chmod 644 {} \;
chmod 755 /path/to/wsgi/scripts/*.py
```

## Endpoints

These routes are mounted directly (no `/api` prefix):

- `GET/POST /login` - Authentication
- `POST /logout` - Logout
- `GET/POST /main` - Submit or query a test
- `GET /pdf` - Retrieve PDF report (session or HMAC token)
- `GET /progress` - Poll progress JSON
- `GET /progress-stream` - SSE progress stream
- `GET /services-config` - Available services and quick ports
- `GET /test-config` - Authenticated test configuration
- `POST /cleanup` - Admin cleanup operations

## Performance Optimizations

1. **Module Preloading**: All Python modules are loaded at startup in `app.wsgi`
2. **RAM-based Storage**: All temporary files in /dev/shm/tsim for minimal I/O:
   - Sessions, run data, scripts, locks, PDFs, matplotlib cache
   - Only logs written to disk (/var/log/tsim)
3. **Direct Imports**: Scripts imported as libraries instead of subprocess calls
4. **Process Isolation**: Background tasks in separate processes with auto-cleanup
5. **Caching**: Results cached in RAM for quick retrieval

## Security Features

- Session-based authentication with secure tokens
- Input validation and sanitization
- CSRF protection via session tokens
- Secure password hashing (SHA256)
- XSS and injection prevention

## Monitoring and Logs

- Application logs: `/var/log/tsim/`
- Apache access logs: `/var/log/apache2/tsim_access.log`
- Apache error logs: `/var/log/apache2/tsim_error.log`

Monitor application performance:
```bash
# View WSGI processes
sudo apache2ctl -M | grep wsgi

# Check process status
ps aux | grep wsgi

# Monitor logs
tail -f /var/log/apache2/tsim_error.log
tail -f /var/log/tsim/tsim.log
```

## Troubleshooting

### Common Issues

1. **500 Internal Server Error**
   - Check Apache error log: `sudo tail -f /var/log/apache2/tsim_error.log`
   - Verify Python path and module imports
   - Check file permissions

2. **Session Issues**
   - Verify /dev/shm/tsim exists and has correct permissions
   - Check if session cleanup is running
   - Monitor disk space on /dev/shm

3. **PDF Generation Fails**
   - Ensure PyPDF2 and matplotlib are installed
   - Check virtual environment activation
   - Verify write permissions on output directories

4. **Slow Performance**
   - Check if all modules are preloaded in app.wsgi
   - Monitor Apache process count
   - Review WSGIDaemonProcess settings

## Development

### Testing Locally

```bash
# Option A: mod_wsgi-express (recommended)
mod_wsgi-express start-server wsgi/app.wsgi --port 8000

# Option B: simple built-in server
python3 wsgi/run_local.py         # serves http://localhost:8000
PORT=8080 python3 wsgi/run_local.py

# Then visit http://localhost:8000/
```

### Adding New Handlers

1. Create handler in `handlers/` with `Tsim` prefix
2. Import in `app.wsgi` for preloading
3. Add route in `tsim_app.py`
4. Update `htdocs/js/api.js` if needed

## Migration from CGI

This WSGI implementation is designed to run alongside the existing CGI system during migration:

1. Both systems can coexist on different URLs
2. Sessions are independent between systems
3. Gradual migration possible by updating frontend URLs
4. No shared state between CGI and WSGI

## Support

For issues or questions about the WSGI deployment:
1. Check the logs in `/var/log/tsim/` and `/var/log/apache2/`
2. Verify configuration in `config.json`
3. Ensure all Python dependencies are installed
4. Review Apache mod_wsgi documentation

## License

[Include appropriate license information]

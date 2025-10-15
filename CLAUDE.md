# CLAUDE_CLEAN.md

This file provides guidance for Claude Code (claude.ai/code) when working with code in this repository, focusing on usage, automation, and development standards.

[... existing content remains unchanged ...]

## WSGI/Apache Debugging Protocol

When investigating issues with WSGI services, follow this protocol to avoid wasting time:

### 1. First Action: Check Existing Logs

Always check existing error logs BEFORE adding debug logging or making code changes:

```bash
# Find all errors in last 10 minutes
sudo grep -E "ERROR|CRITICAL" /var/log/tsim/apache-error.log | tail -50

# Search for specific component errors with context
sudo grep -B5 -A5 "tsim.simulators.host_namespace_setup.*ERROR" /var/log/tsim/apache-error.log

# Find errors for specific run_id/job
sudo grep "run_id_here" /var/log/tsim/apache-error.log | grep ERROR

# Search by timestamp window (e.g., Oct 16 between 00:20 and 00:30)
sudo grep "Oct 16 00:2[0-9]:" /var/log/tsim/apache-error.log | grep ERROR
```

### 2. Component Log Mapping

Different components use different logger names:

- `tsim.ksms` - WSGI KSMS service errors
- `tsim.simulators.host_namespace_setup` - Direct HostNamespaceManager/script errors
- `tsim.scheduler` - Queue and job scheduling
- `tsim.hybrid_executor` - Background execution (process/thread pools)
- `tsim.reconciler` - Job state reconciliation
- `tsim.app` - Request routing and endpoints
- `tsim.performance` - Request timing and metrics

### 3. Only Add Debug Logging If

- Existing errors don't explain the root cause
- Need to track execution flow between components
- Existing log level is too high (WARNING when you need INFO/DEBUG)
- Need to verify a code path is being executed

### 4. Common Silent Failure Patterns

When errors appear to be "silent", check:

- Logger is properly configured with handlers
- Log level allows the message through (ERROR > WARNING > INFO > DEBUG)
- Exceptions caught without re-raising or logging
- Functions returning False/None without logging the reason
- Component initialization without calling required setup methods (e.g., `load_router_facts()`)

### 5. WSGI-Specific Issues

- mod_wsgi runs as `www-data:www-data` (apache-site.conf)
- Logging configured via `logging.basicConfig()` in app.wsgi outputs to stderr → apache-error.log
- Request timeout: 60s, Inactivity timeout: 300s (5 min)
- When daemon process times out, mod_wsgi dumps thread stack traces - this is normal debugging output
- HostNamespaceManager instantiated in WSGI must call `load_router_facts()` and `discover_namespaces()` after construction

## Development Memory

- Do not commit anything yourself without asking
- Always run sudo with '-E' argument to pick up environment
- Do not print any informational or summary messages from any command when -j option has been set, unless verbose option has been set too
- Always execute tsimsh from top level directory and pipe script via stdin to it
- Always cat script to stdout and pipe to tsimsh:  'cat script.tsim | ./tsimsh'
- Never use operating system commands to start/stop/kill processes or do anything else related to namespaces and their corresponding objects. ALWAYS use tsimsh commands or make targets instead.
- When creating new python script, set shebang line to: '#!/usr/bin/env -S python3 -B -u'
- you shall never use any other source of facts except for directory referenced by TRACEROUTE_SIMULATOR_RAW_FACTS envvar. If this envvar is not defined, or directory it points to does not exist or it does not contain valid raw fact files, raise critical exception and exit.
- you shall never execute any python script with sudo from command line
- YOU SHALL NEVER DO 2>&1 when executing scripts
- never try to use 'ls' outside of your working directory. use 'find' with filtering and -exec option instead.
- always use tsimsh from PATH, never from repository
- for all searches, edits, updates use code from repository only
- always use -q option to tsimsh when executing batch commands
- NEVER UPDATE INSTALLATION!!!!!
- always add -q flag when executing tsimsh
- do not support running in development mode - just package mode
- search and work on files in repo only
- do not commit without asking
- don't use emojis when writing documents
- do not install anything or restart apache2 without permission
- use unix_group parameter, do not hardcode tsim-users into scripts
- all directories in /dev/shm/tsim must have following permissions: 2775 and all group ownerships must be set to unix_group parameter.
all files in /dev/shm/tsim must have following permissions: 0660 and all group ownerships must be set to unix_group parameter.
- never execute any python script as root using sudo!
# CLAUDE_CLEAN.md

This file provides guidance for Claude Code (claude.ai/code) when working with code in this repository, focusing on usage, automation, and development standards.

[... existing content remains unchanged ...]

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
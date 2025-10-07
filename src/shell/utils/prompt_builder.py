#!/usr/bin/env -S python3 -B -u
"""
Bash-like prompt builder for tsimsh.

Provides sophisticated prompt generation that mimics bash PS1 prompts including:
- Current hostname
- Current working directory
- Python virtual environment
- Git branch and status
- User information
"""

import os
import sys
import pwd
import socket
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class PromptBuilder:
    """Build bash-like prompts for tsimsh."""

    def __init__(self, version: str):
        """
        Initialize prompt builder.

        Args:
            version: tsimsh version string
        """
        self.version = version
        self.is_bash_shell = self._detect_bash_shell()

    def _detect_bash_shell(self) -> bool:
        """Detect if user's shell is bash."""
        try:
            shell = os.environ.get('SHELL', '')
            return 'bash' in shell.lower()
        except Exception:
            return False

    def _get_username(self) -> str:
        """Get current username."""
        try:
            return pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            return os.environ.get('USER', 'user')

    def _get_hostname(self) -> str:
        """Get short hostname."""
        try:
            hostname = socket.gethostname()
            # Return short hostname (before first dot)
            return hostname.split('.')[0]
        except Exception:
            return 'localhost'

    def _get_cwd(self) -> str:
        """Get current working directory with home replacement."""
        try:
            cwd = os.getcwd()
            home = os.path.expanduser('~')
            if cwd.startswith(home):
                return '~' + cwd[len(home):]
            return cwd
        except Exception:
            return '~'

    def _get_venv(self) -> Optional[str]:
        """Get active Python virtual environment name."""
        venv = os.environ.get('VIRTUAL_ENV')
        if venv:
            return Path(venv).name

        # Check for conda environment
        conda_env = os.environ.get('CONDA_DEFAULT_ENV')
        if conda_env and conda_env != 'base':
            return conda_env

        return None

    def _get_git_info(self) -> Tuple[Optional[str], str]:
        """
        Get git branch and status for current directory with bash-git-prompt style indicators.

        Returns:
            Tuple of (branch_name, status_string)
            status_string: Rich status with symbols like bash-git-prompt:
            - ✔ clean
            - ●n staged files
            - ✚n changed files
            - …n untracked files
            - ✖n conflicts
            - ↑n commits ahead
            - ↓n commits behind
        """
        try:
            # Check if we're in a git repository
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode != 0:
                return None, ''

            # Get current branch
            result = subprocess.run(
                ['git', 'symbolic-ref', '--short', 'HEAD'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.returncode != 0:
                # Detached HEAD state
                result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                branch = result.stdout.strip() if result.returncode == 0 else 'unknown'
            else:
                branch = result.stdout.strip()

            # Get porcelain status
            result = subprocess.run(
                ['git', 'status', '--porcelain', '--branch'],
                capture_output=True,
                text=True,
                timeout=1
            )

            if result.returncode != 0:
                return branch, ''

            lines = result.stdout.strip().split('\n')

            # Parse counts
            staged = 0
            changed = 0
            untracked = 0
            conflicts = 0
            ahead = 0
            behind = 0

            for line in lines:
                if line.startswith('##'):
                    # Branch line - parse ahead/behind
                    if '[ahead' in line:
                        import re
                        match = re.search(r'ahead (\d+)', line)
                        if match:
                            ahead = int(match.group(1))
                    if '[behind' in line or 'behind' in line:
                        import re
                        match = re.search(r'behind (\d+)', line)
                        if match:
                            behind = int(match.group(1))
                elif line.startswith('??'):
                    untracked += 1
                elif line.startswith('UU') or line.startswith('AA') or line.startswith('DD'):
                    conflicts += 1
                else:
                    # Check first two chars for index and working tree status
                    if len(line) >= 2:
                        index_status = line[0]
                        work_status = line[1]

                        # Staged changes (index has changes)
                        if index_status in 'MADRC':
                            staged += 1
                        # Working tree changes
                        if work_status in 'MD':
                            changed += 1

            # Build status string with symbols
            status_parts = []

            if conflicts > 0:
                status_parts.append(f'✖{conflicts}')
            if staged > 0:
                status_parts.append(f'●{staged}')
            if changed > 0:
                status_parts.append(f'✚{changed}')
            if untracked > 0:
                status_parts.append(f'…{untracked}')
            if ahead > 0:
                status_parts.append(f'↑{ahead}')
            if behind > 0:
                status_parts.append(f'↓{behind}')

            if not status_parts:
                status = '✔'  # Clean
            else:
                status = '|' + '|'.join(status_parts)

            return branch, status

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None, ''

    def build_simple_prompt(self) -> str:
        """Build simple fallback prompt when not using bash."""
        return f"tsimsh-{self.version}> "

    def build_bash_like_prompt(self, use_colors: bool = True) -> str:
        """
        Build bash-like prompt with full features.

        Args:
            use_colors: Whether to use ANSI color codes

        Returns:
            Formatted prompt string
        """
        parts = []

        # Color codes (if enabled)
        if use_colors:
            try:
                from colorama import Fore, Style
                GREEN = Fore.GREEN
                BLUE = Fore.BLUE
                YELLOW = Fore.YELLOW
                CYAN = Fore.CYAN
                RED = Fore.RED
                RESET = Style.RESET_ALL
            except ImportError:
                GREEN = BLUE = YELLOW = CYAN = RED = RESET = ''
        else:
            GREEN = BLUE = YELLOW = CYAN = RED = RESET = ''

        # Add virtual environment if active
        venv = self._get_venv()
        if venv:
            parts.append(f"{YELLOW}({venv}){RESET}")

        # Add user@host
        username = self._get_username()
        hostname = self._get_hostname()
        parts.append(f"{GREEN}{username}@{hostname}{RESET}")

        # Add current directory
        cwd = self._get_cwd()
        parts.append(f"{BLUE}{cwd}{RESET}")

        # Add git info if in git repository
        branch, status = self._get_git_info()
        if branch:
            git_str = f"{CYAN}({branch}{status}){RESET}"
            parts.append(git_str)

        # Join first line parts
        first_line = ' '.join(parts)

        # Add tsimsh on second line with prompt symbol
        second_line = f"{GREEN}tsimsh-{self.version}{RESET}> "

        # Combine with newline
        prompt = first_line + '\n' + second_line

        return prompt

    def build_prompt(self, use_colors: bool = True) -> str:
        """
        Build appropriate prompt based on user's shell.

        Args:
            use_colors: Whether to use ANSI color codes

        Returns:
            Formatted prompt string
        """
        if self.is_bash_shell:
            return self.build_bash_like_prompt(use_colors)
        else:
            return self.build_simple_prompt()

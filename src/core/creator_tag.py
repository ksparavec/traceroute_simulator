#!/usr/bin/env -S python3 -B -u
"""Creator Tag Management

Provides centralized creator tag detection and formatting for all resource types:
- Hosts (dynamic namespace hosts)
- Routers (created via network setup)
- Services (echo services for testing)

Format: "method:username"
Examples: "wsgi:bob", "cli:alice", "api:api_user"

Used for:
- Audit trails
- Resource cleanup (e.g., removing WSGI-created resources on daemon restart)
- Access control (future)
"""

import os
from typing import Optional


class CreatorTagManager:
    """Manages creator tag detection and formatting"""

    # Environment variable for WSGI to set logged-in username
    ENV_WSGI_USERNAME = 'TSIM_WSGI_USERNAME'

    # Environment variable for API to set authenticated user
    ENV_API_USERNAME = 'TSIM_API_USERNAME'

    # Standard Unix username environment variable
    ENV_UNIX_USER = 'USER'

    @staticmethod
    def get_creator_tag() -> str:
        """Auto-detect and return creator tag in format 'method:username'.

        Detection logic:
        1. Detect execution context (WSGI, API, or CLI)
        2. Get username from appropriate source
        3. Format as 'method:username'

        WSGI detection:
        - Checks for mod_wsgi environment variables
        - Uses TSIM_WSGI_USERNAME if set (logged-in user from session)
        - Falls back to $USER (typically 'www-data')

        API detection:
        - Checks for TSIM_API_CALL marker
        - Uses TSIM_API_USERNAME if set

        CLI detection:
        - Default if not WSGI or API
        - Uses $USER environment variable

        Returns:
            Creator tag string (e.g., 'wsgi:bob', 'cli:alice')
            Never returns None - always provides a tag
        """
        method, username = CreatorTagManager._detect_context()
        return f"{method}:{username}"

    @staticmethod
    def _detect_context() -> tuple[str, str]:
        """Detect execution context and username.

        Returns:
            Tuple of (method, username)
        """
        # Check for WSGI context
        if CreatorTagManager._is_wsgi_context():
            method = 'wsgi'
            # WSGI should set the logged-in username
            username = os.environ.get(CreatorTagManager.ENV_WSGI_USERNAME)
            if not username:
                # Fallback to process user (typically www-data)
                username = os.environ.get(CreatorTagManager.ENV_UNIX_USER, 'www-data')

        # Check for API context
        elif os.environ.get('TSIM_API_CALL'):
            method = 'api'
            username = os.environ.get(CreatorTagManager.ENV_API_USERNAME, 'api_user')

        # Default to CLI
        else:
            method = 'cli'
            username = os.environ.get(CreatorTagManager.ENV_UNIX_USER, 'unknown')

        return method, username

    @staticmethod
    def _is_wsgi_context() -> bool:
        """Check if running in WSGI context.

        Returns:
            True if WSGI environment detected
        """
        # mod_wsgi sets these environment variables
        return bool(
            os.environ.get('WSGI_MULTITHREAD') or
            os.environ.get('mod_wsgi.listener_host') or
            os.environ.get('wsgi.version')
        )

    @staticmethod
    def parse_creator_tag(tag: str) -> Optional[tuple[str, str]]:
        """Parse a creator tag into method and username.

        Args:
            tag: Creator tag string (e.g., 'wsgi:bob')

        Returns:
            Tuple of (method, username) or None if invalid format
        """
        if not tag or ':' not in tag:
            return None

        parts = tag.split(':', 1)
        if len(parts) != 2:
            return None

        return parts[0], parts[1]

    @staticmethod
    def is_wsgi_created(tag: str) -> bool:
        """Check if a resource was created by WSGI.

        Args:
            tag: Creator tag string

        Returns:
            True if created by WSGI
        """
        parsed = CreatorTagManager.parse_creator_tag(tag)
        return parsed is not None and parsed[0] == 'wsgi'

    @staticmethod
    def is_cli_created(tag: str) -> bool:
        """Check if a resource was created by CLI.

        Args:
            tag: Creator tag string

        Returns:
            True if created by CLI
        """
        parsed = CreatorTagManager.parse_creator_tag(tag)
        return parsed is not None and parsed[0] == 'cli'

    @staticmethod
    def is_api_created(tag: str) -> bool:
        """Check if a resource was created by API.

        Args:
            tag: Creator tag string

        Returns:
            True if created by API
        """
        parsed = CreatorTagManager.parse_creator_tag(tag)
        return parsed is not None and parsed[0] == 'api'

    @staticmethod
    def get_username_from_tag(tag: str) -> Optional[str]:
        """Extract username from creator tag.

        Args:
            tag: Creator tag string

        Returns:
            Username or None if invalid format
        """
        parsed = CreatorTagManager.parse_creator_tag(tag)
        return parsed[1] if parsed else None

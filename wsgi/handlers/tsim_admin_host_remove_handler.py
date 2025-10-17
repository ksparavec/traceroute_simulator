#!/usr/bin/env -S python3 -B -u
"""
TSIM Admin Host Remove Handler
Provides admin-only endpoint to manually remove hosts from the pool.
"""

import json
import logging
from typing import Dict, Any, List
from .tsim_base_handler import TsimBaseHandler


class TsimAdminHostRemoveHandler(TsimBaseHandler):
    """Admin endpoint for manual host removal

    Allows admins to manually remove hosts from the host pool.
    Hosts can only be removed if they are not currently in use by any jobs.
    """

    def __init__(self, config_service, session_manager, logger_service, scheduler=None):
        super().__init__(session_manager, logger_service)
        self.config = config_service
        self.scheduler = scheduler
        self.logger = logging.getLogger('tsim.handler.admin_host_remove')

    def handle(self, environ: Dict[str, Any], start_response) -> List[bytes]:
        session = self.validate_session(environ)
        if not session:
            return self.error_response(start_response, 'Authentication required', '401 Unauthorized')
        if session.get('role') != 'admin':
            return self.error_response(start_response, 'Admin access required', '403 Forbidden')

        method = environ.get('REQUEST_METHOD', 'POST')
        if method != 'POST':
            return self.error_response(start_response, 'Method not allowed', '405 Method Not Allowed')

        # Parse request body for host_name
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
            if content_length == 0:
                return self.error_response(start_response, 'Missing request body', '400 Bad Request')

            request_body = environ['wsgi.input'].read(content_length).decode('utf-8')
            data = json.loads(request_body)
            host_name = data.get('host_name')

            if not host_name:
                return self.error_response(start_response, 'Missing host_name parameter', '400 Bad Request')

        except Exception as e:
            self.logger.error(f"Error parsing request: {e}")
            return self.error_response(start_response, f'Invalid request: {e}', '400 Bad Request')

        # Check if host pool is available
        if not self.scheduler or not hasattr(self.scheduler, 'host_pool') or not self.scheduler.host_pool:
            self.logger.error("Host pool not available")
            return self.error_response(start_response, 'Host pool service not available', '503 Service Unavailable')

        # Attempt to remove the host
        try:
            result = self.scheduler.host_pool.remove_host_manual(host_name)

            if result['success']:
                self.logger.info(f"Admin {session.get('username')} removed host {host_name}")
                return self.json_response(start_response, result, '200 OK')
            else:
                self.logger.warning(f"Failed to remove host {host_name}: {result['message']}")
                return self.json_response(start_response, result, '400 Bad Request')

        except Exception as e:
            self.logger.error(f"Error removing host {host_name}: {e}")
            return self.error_response(start_response, f'Internal error: {e}', '500 Internal Server Error')

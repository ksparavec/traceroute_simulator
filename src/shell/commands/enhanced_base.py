#!/usr/bin/env -S python3 -B -u
"""
Enhanced base command handler with unified interface support.
"""

import os
import sys
import json
import subprocess
import argparse
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from io import StringIO

try:
    from cmd2 import Cmd2ArgumentParser
except ImportError:
    from argparse import ArgumentParser as Cmd2ArgumentParser

from .base import BaseCommandHandler


class EnhancedCommandHandler(BaseCommandHandler):
    """Enhanced base class with unified interface for all commands."""
    
    def __init__(self, shell):
        super().__init__(shell)
        self._last_return_code = 0
        self._last_output = ""
        self._captured_json = None
    
    @abstractmethod
    def get_command_name(self) -> str:
        """Get the command name (e.g., 'trace', 'facts')."""
        pass
    
    @abstractmethod
    def get_command_help(self) -> Dict[str, Any]:
        """
        Get comprehensive help information for the command.
        
        Returns:
            Dict with keys:
                - description: str - Command description
                - usage: List[str] - Usage examples
                - mandatory_options: Dict[str, str] - Mandatory options with descriptions
                - optional_options: Dict[str, str] - Optional options with descriptions
                - examples: List[Dict[str, str]] - Examples with description and command
        """
        pass
    
    def handle_command(self, args: str) -> Optional[int]:
        """Enhanced command handler with return value capture."""
        # Reset captured values
        self._last_return_code = 0
        self._last_output = ""
        self._captured_json = None
        
        # Check for help flags first
        args_list = args.strip().split()
        if args_list and args_list[0] in ['--help', '-h']:
            self.show_detailed_help()
            self._update_shell_variables(0)
            return None
        
        # Capture output if command might produce JSON
        old_stdout = sys.stdout
        output_buffer = StringIO()
        
        try:
            # Check if JSON output is requested
            produces_json = '--json' in args or '-j' in args
            if produces_json:
                sys.stdout = output_buffer
            
            # Execute the command
            return_code = self._handle_command_impl(args)
            if return_code is None:
                return_code = 0
            
            # Capture output if it was JSON
            if produces_json:
                self._last_output = output_buffer.getvalue()
                # Try to parse as JSON
                try:
                    self._captured_json = json.loads(self._last_output)
                except json.JSONDecodeError:
                    # Not valid JSON, just store as string
                    pass
            
            self._last_return_code = return_code
            self._update_shell_variables(return_code)
            
            # Never exit the shell
            return None
            
        except SystemExit as e:
            # Prevent shell exit
            self._last_return_code = e.code if isinstance(e.code, int) else 1
            self._update_shell_variables(self._last_return_code)
            return None
        except Exception as e:
            self.error(f"Command failed: {e}")
            if hasattr(self.shell, 'verbose') and self.shell.verbose:
                import traceback
                traceback.print_exc()
            self._last_return_code = 1
            self._update_shell_variables(1)
            return None
        finally:
            sys.stdout = old_stdout
            # Print captured output if there was any
            if produces_json and self._last_output:
                self.shell.poutput(self._last_output)
    
    def _update_shell_variables(self, return_code: int):
        """Update shell variables with command results."""
        if hasattr(self.shell, 'variable_manager'):
            # Set return value
            self.shell.variable_manager.set_variable('TSIM_RETURN_VALUE', str(return_code))
            
            # Set result if JSON was captured
            if self._captured_json is not None:
                self.shell.variable_manager.set_variable('TSIM_RESULT', self._captured_json)
            elif self._last_output and ('--json' in self._last_output or '-j' in self._last_output):
                # Try to set string output if it looked like JSON was requested
                self.shell.variable_manager.set_variable('TSIM_RESULT', self._last_output.strip())
    
    def show_detailed_help(self):
        """Show comprehensive help for the command."""
        help_info = self.get_command_help()
        cmd_name = self.get_command_name()
        
        self.shell.poutput(f"\n{self.shell.colorize('COMMAND:', 'cyan')}")
        self.shell.poutput(f"  {cmd_name} - {help_info['description']}")
        
        self.shell.poutput(f"\n{self.shell.colorize('USAGE:', 'cyan')}")
        for usage in help_info.get('usage', []):
            self.shell.poutput(f"  {usage}")
        
        if help_info.get('mandatory_options'):
            self.shell.poutput(f"\n{self.shell.colorize('MANDATORY OPTIONS:', 'cyan')}")
            for opt, desc in help_info['mandatory_options'].items():
                self.shell.poutput(f"  {opt:<20} {desc}")
        
        if help_info.get('optional_options'):
            self.shell.poutput(f"\n{self.shell.colorize('OPTIONAL OPTIONS:', 'cyan')}")
            for opt, desc in help_info['optional_options'].items():
                self.shell.poutput(f"  {opt:<20} {desc}")
        
        if help_info.get('examples'):
            self.shell.poutput(f"\n{self.shell.colorize('EXAMPLES:', 'cyan')}")
            for example in help_info['examples']:
                self.shell.poutput(f"\n  {example.get('description', '')}:")
                self.shell.poutput(f"    {example.get('command', '')}")
        
        self.shell.poutput("")
    
    def parse_arguments(self, args: str, parser: argparse.ArgumentParser) -> Optional[argparse.Namespace]:
        """Parse arguments with help handling."""
        try:
            # Add help flags if not already present
            if '-h' not in parser._option_string_actions and '--help' not in parser._option_string_actions:
                parser.add_argument('-h', '--help', action='store_true', help='Show this help message')
            
            # Parse args
            args_list = args.strip().split() if args.strip() else []
            parsed = parser.parse_args(args_list)
            
            # Check for help flag
            if hasattr(parsed, 'help') and parsed.help:
                self.show_detailed_help()
                return None
            
            return parsed
        except SystemExit:
            # Argument parsing failed - show help
            return None
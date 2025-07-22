"""
Base command handler class for shell commands.
"""

import os
import sys
import subprocess
import argparse
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

try:
    from cmd2 import Cmd2ArgumentParser
except ImportError:
    # Fallback for older cmd2 versions
    from argparse import ArgumentParser as Cmd2ArgumentParser

try:
    import colorama
    from colorama import Fore, Style
    colorama.init()
except ImportError:
    # Fallback if colorama is not available
    class _FallbackColor:
        def __getattr__(self, name):
            return ""
    Fore = _FallbackColor()
    Style = _FallbackColor()


class BaseCommandHandler(ABC):
    """Base class for all command handlers."""
    
    def __init__(self, shell):
        self.shell = shell
        self.project_root = shell.project_root
        self.python_cmd = sys.executable
        
        # Set up facts directory
        self.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
    
    def handle_command(self, args: str) -> Optional[int]:
        """Handle the command with given arguments."""
        try:
            return self._handle_command_impl(args)
        except SystemExit:
            # Catch sys.exit() calls from scripts
            return None  # Return None to keep shell running
        except Exception as e:
            # Catch all other exceptions to prevent shell exit
            self.error(f"Command failed: {e}")
            if hasattr(self.shell, 'verbose') and self.shell.verbose:
                import traceback
                traceback.print_exc()
            return None  # Return None to keep shell running
    
    @abstractmethod
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Implementation of command handling - override in subclasses."""
        pass
    
    def handle_context_command(self, args: str) -> Optional[int]:
        """Handle commands in context mode."""
        # Default implementation - just pass to handle_command
        return self.handle_command(args)
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle the command with parsed arguments."""
        # Default implementation - convert back to string for backward compatibility
        # Subclasses should override this to work with parsed args directly
        args_list = []
        if hasattr(args, 'subcommand') and args.subcommand:
            args_list.append(args.subcommand)
            # Add other arguments
            for key, value in vars(args).items():
                if key != 'subcommand' and value is not None:
                    if isinstance(value, bool) and value:
                        args_list.append(f'--{key.replace("_", "-")}')
                    elif not isinstance(value, bool):
                        args_list.append(f'--{key.replace("_", "-")}')
                        args_list.append(str(value))
        return self.handle_command(' '.join(args_list))
    
    def get_context_completions(self, text: str) -> List[str]:
        """Get completions for context mode."""
        # Default implementation - return subcommand names
        return self.get_subcommand_names()
    
    def get_subcommand_names(self) -> List[str]:
        """Get list of subcommand names - override in subclasses."""
        return []
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for command arguments."""
        # Default implementation - override in subclasses
        return []
    
    def handle_context_completion(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Handle completion in context mode."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        if not args:
            # No arguments yet, complete subcommands
            return self.get_context_completions(text)
        
        # Get the subcommand (first argument)
        subcommand = args[0]
        
        # If we're completing the subcommand itself
        if len(args) == 1 and not line.endswith(' '):
            return self.get_context_completions(text)
        
        # We're completing arguments for the subcommand
        return self.complete_context_arguments(subcommand, text, line, begidx, endidx)
    
    def complete_context_arguments(self, subcommand: str, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Complete arguments for a specific subcommand in context mode."""
        # Default implementation - override in subclasses for specific argument completion
        return []
    
    def run_python_script(self, script_path: str, args: List[str], 
                         use_sudo: bool = False, 
                         cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run a Python script with the given arguments."""
        # Build the command
        cmd = []
        if use_sudo:
            cmd.extend(['sudo', '-E'])
        
        cmd.extend([self.python_cmd, '-u', '-B', script_path] + args)
        
        # Set working directory
        if cwd is None:
            cwd = self.project_root
        
        # Use existing environment variables
        env = os.environ.copy()
        
        try:
            result = subprocess.run(cmd, cwd=cwd, env=env, 
                                  capture_output=True, text=True)
            return result
        except Exception as e:
            # Create a mock result for error handling
            class MockResult:
                def __init__(self, error):
                    self.returncode = 1
                    self.stdout = ""
                    self.stderr = str(error)
            return MockResult(e)
    
    def run_script_with_output(self, script_path: str, args: List[str], 
                              use_sudo: bool = False, 
                              show_output: bool = True) -> int:
        """Run a script and handle output display."""
        result = self.run_python_script(script_path, args, use_sudo=use_sudo)
        
        if show_output:
            if result.stdout:
                self.shell.poutput(result.stdout)
            if result.stderr:
                self.shell.poutput(f"{Fore.RED}{result.stderr}{Style.RESET_ALL}")
        
        return result.returncode
    
    def parse_arguments(self, args_str: str, parser: argparse.ArgumentParser) -> Optional[argparse.Namespace]:
        """Parse command arguments with error handling."""
        try:
            # Split arguments properly
            args_list = self._split_args(args_str)
            return parser.parse_args(args_list)
        except SystemExit:
            # argparse calls sys.exit on error, catch it
            return None
        except Exception as e:
            self.shell.poutput(f"{Fore.RED}Error parsing arguments: {e}{Style.RESET_ALL}")
            return None
    
    def _split_args(self, args_str: str) -> List[str]:
        """Split argument string into list, handling quotes properly."""
        import shlex
        try:
            return shlex.split(args_str)
        except ValueError as e:
            self.shell.poutput(f"{Fore.RED}Error parsing arguments: {e}{Style.RESET_ALL}")
            return []
    
    def _handle_context_exit(self, args_str: str) -> bool:
        """Handle exit commands in context mode."""
        args = args_str.strip().lower()
        if args in ['exit', 'quit', 'q']:
            return True
        return False
    
    def get_script_path(self, script_name: str) -> str:
        """Get the full path to a script in the project."""
        return os.path.join(self.project_root, script_name)
    
    def success(self, message: str):
        """Print success message."""
        self.shell.poutput(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")
    
    def error(self, message: str):
        """Print error message."""
        self.shell.poutput(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")
    
    def warning(self, message: str):
        """Print warning message."""
        self.shell.poutput(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")
    
    def info(self, message: str):
        """Print info message."""
        self.shell.poutput(f"{Fore.CYAN}ℹ {message}{Style.RESET_ALL}")
    
    def check_script_exists(self, script_path: str) -> bool:
        """Check if a script exists."""
        if not os.path.exists(script_path):
            self.error(f"Script not found: {script_path}")
            return False
        return True
    
    def check_facts_directory(self) -> bool:
        """Check if facts directory exists."""
        if not self.facts_dir:
            self.error("TRACEROUTE_SIMULATOR_FACTS environment variable not set")
            return False
        if not os.path.exists(self.facts_dir):
            self.error(f"Facts directory not found: {self.facts_dir}")
            return False
        return True
    
    def show_context_help(self, context_name: str):
        """Show help for context mode."""
        help_method = getattr(self.shell, f'help_{context_name}', None)
        if help_method:
            help_method()
        else:
            self.info(f"No help available for {context_name} context")
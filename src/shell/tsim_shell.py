#!/usr/bin/env -S python3 -B -u

"""
Main TracerouteSimulatorShell class implementation.
"""

import os
import sys
import argparse
import json
import subprocess
from typing import List, Optional

try:
    import cmd2
    from cmd2 import with_argparser, Cmd2ArgumentParser
    from cmd2.history import HistoryItem
except ImportError:
    print("Error: cmd2 is required. Install with: pip install cmd2")
    sys.exit(1)

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

# Import the new VariableManager
from .utils.variable_manager import VariableManager
from .utils.history_handler import HistoryHandler


class TracerouteSimulatorShell(cmd2.Cmd):
    """Interactive shell for traceroute simulator operations."""
    
    # Class attribute for cmd2 compatibility
    orig_rl_history_length = 0
    
    def __init__(self, *args, quick_mode=False, **kwargs):
        # Store quick mode flag
        self.quick_mode = quick_mode
        
        # Detect if we are in an interactive session
        # Check both stdin and stdout to ensure we're in a real terminal
        self.is_interactive = sys.stdin.isatty() and sys.stdout.isatty()

        # Configure persistent history before calling super().__init__
        # Only enable history in interactive mode
        if self.is_interactive:
            history_file = os.path.expanduser('~/.tsimsh_history.json')
            kwargs['persistent_history_file'] = history_file
        else:
            # Disable history in batch mode
            kwargs['persistent_history_file'] = None
        
        # Simple prompt
        self.base_prompt = f"{Fore.GREEN}tsimsh{Style.RESET_ALL}"
        
        # Work around for cmd2 version compatibility issue with orig_rl_history_length
        # This attribute is referenced in some versions of cmd2 but not initialized in others
        # Setting it to 0 prevents AttributeError when cmd2 tries to access it
        # Set this BEFORE calling super().__init__()
        self.orig_rl_history_length = 0
        
        # Set history limit BEFORE calling super().__init__
        # This ensures cmd2 loads the full history
        history_length_env = os.environ.get('TSIM_HISTORY_LENGTH', '1000')
        try:
            history_length = int(history_length_env)
        except ValueError:
            history_length = 1000
        
        # Set the limit that will be used by cmd2 during initialization
        self._persistent_history_length = history_length
        self._configured_history_length = history_length
        
        # Pass persistent_history_length to cmd2's __init__
        kwargs['persistent_history_length'] = history_length
        super().__init__(*args, **kwargs)
        
        # Initialize the VariableManager
        self.variable_manager = VariableManager(self)
        
        # Initialize TSIM_SHOW_LENGTH with default value
        self.variable_manager.set_variable('TSIM_SHOW_LENGTH', '40')
        
        # Initialize TSIM_HISTORY_LENGTH variable from what was already set
        self.variable_manager.set_variable('TSIM_HISTORY_LENGTH', str(self._configured_history_length))
        
        # --- Mode-specific configuration ---
        if self.is_interactive:
            # Shell configuration for interactive mode
            if self.quick_mode:
                self.intro = f"""{Fore.CYAN}
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                        Traceroute Simulator Shell v1.0 (Quick Mode)               ║
║                    Interactive Network Simulation Interface                       ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
Type 'help' for available commands, 'help <command>' for specific command help.
Variables are supported: VAR=value, VAR="value", VAR=$(command). Use $VAR to substitute.
Type 'set' to see all variables.
"""
            else:
                self.intro = f"""{Fore.CYAN}
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                        Traceroute Simulator Shell v1.0                            ║
║                    Interactive Network Simulation Interface                       ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}
Type 'help' for available commands, 'help <command>' for specific command help.
Variables are supported: VAR=value, VAR="value", VAR=$(command). Use $VAR to substitute.
Type 'set' to see all variables.
"""
            self.prompt = f"{self.base_prompt}> "
            # Don't exit on error in interactive mode
            self.quit_on_error = False
        else:
            # Shell configuration for non-interactive (batch) mode
            self.intro = ""
            self.prompt = ""
            # Exit immediately if a command fails in batch mode
            self.quit_on_error = True

        # Get the project root directory
        self.project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Set up facts directory
        self.facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        
        # Initialize command handlers
        self._initialize_handlers()
        
        # Initialize completion only in interactive mode
        self._setup_completion()
        
        # Load configuration if available
        self._load_config()
        
        # Initialize network status variables (both interactive and batch modes)
        self._initialize_network_status()
        
        # Note: .tsimrc is loaded after intro is displayed (see cmdloop override)
    
    def cmdloop(self, intro=None):
        """Override cmdloop to display intro then load .tsimrc."""
        # Store the intro for later use
        if intro is None:
            intro = self.intro
        
        # Display the intro ourselves
        if self.is_interactive and intro:
            self.poutput(intro)
            
        # Load .tsimrc after intro has been displayed (skip in quick mode)
        if self.is_interactive and not self.quick_mode:
            self._load_tsimrc()
            # Apply history length setting after .tsimrc is loaded
            self._apply_history_length()
            
        # Now start the command loop without intro (we already displayed it)
        super().cmdloop(intro="")
    
    def _apply_history_length(self):
        """Apply the TSIM_HISTORY_LENGTH setting to the cmd2 history."""
        # Get the history length from the variable
        try:
            history_length_str = self.variable_manager.get_variable('TSIM_HISTORY_LENGTH')
            if history_length_str:
                history_length = int(history_length_str)
                if history_length > 0:
                    # Store the setting for future reference
                    self._configured_history_length = history_length
                    # Also update cmd2's internal persistent history length
                    self._persistent_history_length = history_length
                    
                    # If current history exceeds the limit, truncate it
                    if len(self.history) > history_length:
                        # cmd2's history.truncate(n) keeps only the last n items
                        self.history.truncate(history_length)
                else:
                    # Invalid value, keep default
                    self._configured_history_length = 1000
                    self._persistent_history_length = 1000
            else:
                # No value set, use default
                self._configured_history_length = 1000
                self._persistent_history_length = 1000
        except (ValueError, TypeError):
            # Invalid value, keep default
            self._configured_history_length = 1000
            self._persistent_history_length = 1000
    
    def _initialize_network_status(self):
        """Initialize TSIM_NETWORK_STATUS and TSIM_NETWORK_ROUTERS variables."""
        # Skip in quick mode
        if self.quick_mode:
            self.variable_manager.set_variable('TSIM_NETWORK_STATUS', {})
            self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', [])
            return
            
        import io
        import json
        
        # Capture the output of 'network status -j'
        output_buffer = io.StringIO()
        original_stdout = self.stdout
        
        try:
            # Redirect stdout to capture output
            self.stdout = output_buffer
            # Execute network status command in JSON format
            self.onecmd_plus_hooks('network status -j', add_to_history=False)
            # Get the captured output
            output = output_buffer.getvalue().strip()
        except Exception as e:
            # On error, set empty values
            self.variable_manager.set_variable('TSIM_NETWORK_STATUS', {})
            self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', [])
            return
        finally:
            # Restore stdout
            self.stdout = original_stdout
        
        # Parse the JSON output
        try:
            if output:
                network_status = json.loads(output)
                # Store the full network status
                self.variable_manager.set_variable('TSIM_NETWORK_STATUS', network_status)
                
                # Extract router names (keys of the network status dict)
                if isinstance(network_status, dict):
                    router_names = list(network_status.keys())
                    self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', router_names)
                else:
                    self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', [])
            else:
                # No output, set empty values
                self.variable_manager.set_variable('TSIM_NETWORK_STATUS', {})
                self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', [])
        except json.JSONDecodeError:
            # If output is not valid JSON, set empty values
            self.variable_manager.set_variable('TSIM_NETWORK_STATUS', {})
            self.variable_manager.set_variable('TSIM_NETWORK_ROUTERS', [])

    def _truncate_value(self, value: str, is_env_var: bool, verbose: bool) -> str:
        """
        Truncate value if needed based on display rules.
        - Environment variables: always full
        - User variables > TSIM_SHOW_LENGTH bytes: show first TSIM_SHOW_LENGTH bytes + ...
        - Verbose mode: always full
        """
        if verbose or is_env_var:
            return value
        
        # Get truncation length from TSIM_SHOW_LENGTH variable (default 40)
        show_length = 40
        try:
            tsim_show_length = self.variable_manager.get_variable('TSIM_SHOW_LENGTH')
            if tsim_show_length:
                show_length = int(tsim_show_length)
                if show_length < 1:
                    show_length = 40  # Revert to default if invalid
        except (ValueError, TypeError):
            pass  # Keep default
        
        if len(value) > show_length:
            return value[:show_length] + "..."
        return value
    
    def do_set(self, args):
        """Display all currently set shell variables."""
        import argparse
        import json
        
        # Parse arguments
        parser = argparse.ArgumentParser(prog='set', add_help=False)
        parser.add_argument('-v', '--verbose', action='store_true', 
                          help='Show full contents of all variables')
        parser.add_argument('-s', '--shell', action='store_true',
                          help='Show only shell (user) variables')
        parser.add_argument('-e', '--env', action='store_true',
                          help='Show only environment variables')
        parser.add_argument('-j', '--json', action='store_true',
                          help='Pretty-print JSON objects')
        parser.add_argument('-h', '--help', action='store_true',
                          help='Show this help message')
        
        try:
            parsed_args = parser.parse_args(args.split() if args else [])
        except SystemExit:
            return
        
        if parsed_args.help:
            self.poutput("NAME:")
            self.poutput("  set - Display shell and/or environment variables")
            self.poutput("\nUSAGE:")
            self.poutput("  set [-v|--verbose] [-s|--shell] [-e|--env] [-j|--json] [-h|--help]")
            self.poutput("\nOPTIONS:")
            self.poutput("  -v, --verbose    Show full contents of all variables")
            self.poutput("  -s, --shell      Show only shell (user) variables")
            self.poutput("  -e, --env        Show only environment variables")
            self.poutput("  -j, --json       Pretty-print JSON objects")
            self.poutput("  -h, --help       Show this help message")
            self.poutput("\nVARIABLE TYPES:")
            self.poutput("  E = Environment variable (always shown in full)")
            self.poutput("  * = User variable shadowing an environment variable")
            self.poutput("    = User-defined variable")
            self.poutput("\nDISPLAY RULES:")
            self.poutput("  - Variables > TSIM_SHOW_LENGTH bytes show first TSIM_SHOW_LENGTH bytes + ...")
            self.poutput("  - Variables <= TSIM_SHOW_LENGTH bytes shown in full")
            self.poutput("  - Environment variables always shown in full")
            self.poutput("  - TSIM_SHOW_LENGTH defaults to 40 (configurable)")
            self.poutput("\nEXAMPLES:")
            self.poutput("  set              # Show all variables (shortened)")
            self.poutput("  set -v           # Show all variables in full")
            self.poutput("  set -s           # Show only shell variables")
            self.poutput("  set -e           # Show only environment variables")
            return
        
        # Get all variable names (user variables + environment variables)
        user_vars = set(self.variable_manager.variables.keys())
        env_vars = set(os.environ.keys())
        
        # Filter based on options
        if parsed_args.shell and parsed_args.env:
            # Both specified, show all
            vars_to_show = user_vars | env_vars
        elif parsed_args.shell:
            # Only shell variables
            vars_to_show = user_vars
        elif parsed_args.env:
            # Only environment variables (not shadowed)
            vars_to_show = env_vars - user_vars
        else:
            # Default: show all
            vars_to_show = user_vars | env_vars
        
        # Sort for consistent display
        sorted_vars = sorted(vars_to_show)
        
        self.poutput(f"{Fore.CYAN}--- Shell Variables ---{Style.RESET_ALL}")
        if not sorted_vars:
            self.poutput("No variables set.")
            return

        for key in sorted_vars:
            # Check if it's a user variable (which shadows env var)
            if key in self.variable_manager.variables:
                value = self.variable_manager.variables[key]
                # Mark shadowed environment variables
                if key in os.environ:
                    prefix = f"{Fore.YELLOW}*{Style.RESET_ALL}"  # Asterisk indicates shadowing
                else:
                    prefix = " "
            else:
                # It's an environment variable
                value = os.environ[key]
                prefix = f"{Fore.BLUE}E{Style.RESET_ALL}"  # E indicates environment variable
            # Determine if this is an environment-only variable
            is_env_only = key not in self.variable_manager.variables
            
            if isinstance(value, dict):
                if parsed_args.json:
                    # Pretty-print JSON
                    val_str = json.dumps(value, indent=2)
                    self.poutput(f"{prefix} {Fore.GREEN}{key}{Style.RESET_ALL} = ")
                    for line in val_str.split('\n'):
                        self.poutput(f"    {line}")
                else:
                    # For JSON, show truncated JSON string if needed
                    json_str = json.dumps(value, separators=(',', ':'))
                    truncated = self._truncate_value(json_str, is_env_only, parsed_args.verbose)
                    self.poutput(f"{prefix} {Fore.GREEN}{key}{Style.RESET_ALL} = {truncated}")
            elif isinstance(value, list):
                if parsed_args.json:
                    # Pretty-print JSON
                    val_str = json.dumps(value, indent=2)
                    self.poutput(f"{prefix} {Fore.GREEN}{key}{Style.RESET_ALL} = ")
                    for line in val_str.split('\n'):
                        self.poutput(f"    {line}")
                else:
                    # For lists, show truncated JSON string if needed
                    json_str = json.dumps(value, separators=(',', ':'))
                    truncated = self._truncate_value(json_str, is_env_only, parsed_args.verbose)
                    self.poutput(f"{prefix} {Fore.GREEN}{key}{Style.RESET_ALL} = {truncated}")
            else:
                # String value - apply truncation rules
                truncated = self._truncate_value(str(value), is_env_only, parsed_args.verbose)
                self.poutput(f"{prefix} {Fore.GREEN}{key}{Style.RESET_ALL} = \"{truncated}\"")

    def do_export(self, args):
        """Set environment variables for subprocesses."""
        import argparse
        
        # Parse arguments
        parser = argparse.ArgumentParser(prog='export', add_help=False)
        parser.add_argument('-h', '--help', action='store_true',
                          help='Show this help message')
        parser.add_argument('assignments', nargs='*', 
                          help='Variable assignments (VAR=value) or variable names to export')
        
        try:
            parsed_args = parser.parse_args(args.split() if args else [])
        except SystemExit:
            return
        
        if parsed_args.help:
            self.poutput("NAME:")
            self.poutput("  export - Set environment variables for subprocesses")
            self.poutput("\nUSAGE:")
            self.poutput("  export [VAR=value ...]     # Set environment variables")
            self.poutput("  export [VAR ...]           # Export shell variables to environment")
            self.poutput("  export -h|--help           # Show this help")
            self.poutput("\nDESCRIPTION:")
            self.poutput("  Sets environment variables that will be inherited by subprocess commands")
            self.poutput("  like ksms_tester. Variables set with 'export' affect subprocess execution,")
            self.poutput("  unlike 'set' which only affects shell variable substitution.")
            self.poutput("\nEXAMPLES:")
            self.poutput(f"  {Fore.GREEN}export KSMS_JOB_DSCP=35{Style.RESET_ALL}              # Set DSCP for ksms_tester")
            self.poutput(f"  {Fore.GREEN}export DEBUG=1 VERBOSE=2{Style.RESET_ALL}             # Set multiple variables")
            self.poutput(f"  {Fore.GREEN}export PATH{Style.RESET_ALL}                          # Export shell variable to env")
            return
        
        if not parsed_args.assignments:
            # No arguments - show all exported environment variables
            self.poutput(f"{Fore.CYAN}Environment variables:{Style.RESET_ALL}")
            env_vars = dict(os.environ)
            for key in sorted(env_vars.keys()):
                value = env_vars[key]
                # Truncate long values
                if len(value) > 80:
                    display_value = value[:77] + "..."
                else:
                    display_value = value
                self.poutput(f"  {Fore.GREEN}{key}{Style.RESET_ALL}={display_value}")
            return
        
        # Process assignments
        for assignment in parsed_args.assignments:
            if '=' in assignment:
                # VAR=value format
                try:
                    var_name, var_value = assignment.split('=', 1)
                    var_name = var_name.strip()
                    
                    # Validate variable name
                    if not var_name.isidentifier():
                        self.poutput(f"{Fore.RED}Error: Invalid variable name '{var_name}'{Style.RESET_ALL}")
                        continue
                    
                    # Set environment variable
                    os.environ[var_name] = var_value
                    self.poutput(f"Exported: {Fore.GREEN}{var_name}{Style.RESET_ALL}={var_value}")
                    
                except ValueError:
                    self.poutput(f"{Fore.RED}Error: Invalid assignment '{assignment}'{Style.RESET_ALL}")
            else:
                # Just variable name - export from shell variables
                var_name = assignment.strip()
                
                if var_name in self.variable_manager.variables:
                    # Export shell variable to environment
                    value = str(self.variable_manager.variables[var_name])
                    os.environ[var_name] = value
                    self.poutput(f"Exported: {Fore.GREEN}{var_name}{Style.RESET_ALL}={value}")
                else:
                    self.poutput(f"{Fore.RED}Error: Shell variable '{var_name}' not found{Style.RESET_ALL}")

    def do_show(self, args):
        """Display the contents of a specific shell variable."""
        import argparse
        
        # Parse arguments
        parser = argparse.ArgumentParser(prog='show', add_help=False)
        parser.add_argument('variable', nargs='?', help='Variable name to show')
        parser.add_argument('-v', '--verbose', action='store_true', 
                          help='Show full contents of all variables')
        parser.add_argument('-s', '--shell', action='store_true',
                          help='Show only shell (user) variables')
        parser.add_argument('-e', '--env', action='store_true',
                          help='Show only environment variables')
        parser.add_argument('-j', '--json', action='store_true',
                          help='Pretty-print JSON objects')
        parser.add_argument('-h', '--help', action='store_true',
                          help='Show this help message')
        
        try:
            parsed_args = parser.parse_args(args.split() if args else [])
        except SystemExit:
            return
        
        if parsed_args.help:
            self.poutput("NAME:")
            self.poutput("  show - Display shell and/or environment variables")
            self.poutput("\nUSAGE:")
            self.poutput("  show [VARIABLE] [-v|--verbose] [-s|--shell] [-e|--env] [-j|--json] [-h|--help]")
            self.poutput("\nOPTIONS:")
            self.poutput("  -v, --verbose    Show full contents of all variables")
            self.poutput("  -s, --shell      Show only shell (user) variables")
            self.poutput("  -e, --env        Show only environment variables")
            self.poutput("  -j, --json       Pretty-print JSON objects")
            self.poutput("  -h, --help       Show this help message")
            self.poutput("\nEXAMPLES:")
            self.poutput("  show TSIM_RESULT         # Show specific variable")
            self.poutput("  show TSIM_RESULT -v      # Show variable with full content")
            self.poutput("  show TSIM_RESULT -j      # Pretty-print JSON variable")
            self.poutput("  show -s                  # Show all shell variables")
            self.poutput("  show -e                  # Show all environment variables")
            return
        
        # If no variable specified, show all variables with filters
        if not parsed_args.variable:
            # Call do_set with appropriate filters
            set_args = []
            if parsed_args.verbose:
                set_args.append('-v')
            if parsed_args.shell:
                set_args.append('-s')
            if parsed_args.env:
                set_args.append('-e')
            if parsed_args.json:
                set_args.append('-j')
            self.do_set(' '.join(set_args))
            return
        
        # Check if variable exists
        var_name = parsed_args.variable
        if var_name.startswith('$'):
            var_name = var_name[1:]  # Remove $ prefix if present
            
        value = self.variable_manager.get_variable(var_name)
        if value is None:
            self.poutput(f"{Fore.YELLOW}Variable '{var_name}' is not set{Style.RESET_ALL}")
            return
        
        # Determine variable type
        is_user_var = var_name in self.variable_manager.variables
        is_env_var = var_name in os.environ
        is_env_only = not is_user_var and is_env_var
        
        if is_user_var and is_env_var:
            var_type = "(user variable, shadows environment)"
        elif is_user_var:
            var_type = "(user variable)"
        else:
            var_type = "(environment variable)"
        
        # Display the variable
        if isinstance(value, dict):
            if parsed_args.json:
                # Pretty-print JSON
                val_str = json.dumps(value, indent=2)
                self.poutput(f"{Fore.GREEN}{var_name}{Style.RESET_ALL} {var_type} = ")
                for line in val_str.split('\n'):
                    self.poutput(f"  {line}")
            else:
                # Use truncation for dict display
                json_str = json.dumps(value, separators=(',', ':'))
                truncated = self._truncate_value(json_str, is_env_only, parsed_args.verbose)
                self.poutput(f"{Fore.GREEN}{var_name}{Style.RESET_ALL} {var_type} = {truncated}")
        elif isinstance(value, list):
            if parsed_args.json:
                # Pretty-print JSON
                val_str = json.dumps(value, indent=2)
                self.poutput(f"{Fore.GREEN}{var_name}{Style.RESET_ALL} {var_type} = ")
                for line in val_str.split('\n'):
                    self.poutput(f"  {line}")
            else:
                # Use truncation for list display
                json_str = json.dumps(value, separators=(',', ':'))
                truncated = self._truncate_value(json_str, is_env_only, parsed_args.verbose)
                self.poutput(f"{Fore.GREEN}{var_name}{Style.RESET_ALL} {var_type} = {truncated}")
        else:
            # String value - apply truncation rules
            truncated = self._truncate_value(str(value), is_env_only, parsed_args.verbose)
            self.poutput(f"{Fore.GREEN}{var_name}{Style.RESET_ALL} {var_type} = \"{truncated}\"")
    
    def do_unset(self, args):
        """Remove a shell variable from the namespace."""
        import argparse
        
        # Parse arguments
        parser = argparse.ArgumentParser(prog='unset', add_help=False)
        parser.add_argument('variable', nargs='?', help='Variable name to unset')
        parser.add_argument('-h', '--help', action='store_true',
                          help='Show this help message')
        
        try:
            parsed_args = parser.parse_args(args.split() if args else [])
        except SystemExit:
            return
        
        if parsed_args.help or not parsed_args.variable:
            self.poutput("NAME:")
            self.poutput("  unset - Remove a shell variable from the namespace")
            self.poutput("\nUSAGE:")
            self.poutput("  unset VARIABLE [-h|--help]")
            self.poutput("\nDESCRIPTION:")
            self.poutput("  Removes the specified variable completely from the shell environment.")
            self.poutput("  This is similar to unset in bash - the variable will no longer exist.")
            self.poutput("\nEXAMPLES:")
            self.poutput("  unset TSIM_RESULT       # Remove TSIM_RESULT variable")
            self.poutput("  unset MY_VAR            # Remove custom variable")
            return
        
        # Remove the variable
        var_name = parsed_args.variable
        if var_name.startswith('$'):
            var_name = var_name[1:]  # Remove $ prefix if present
        
        if self.variable_manager.unset_variable(var_name):
            self.poutput(f"{Fore.GREEN}Variable '{var_name}' has been unset{Style.RESET_ALL}")
        else:
            self.poutput(f"{Fore.YELLOW}Variable '{var_name}' was not set{Style.RESET_ALL}")
    
    def postcmd(self, stop: bool, statement: cmd2.Statement) -> bool:
        """
        This hook is called after the command is executed.
        We use it to enforce history length limits.
        """
        # Apply history length limit after each command
        if self.is_interactive and hasattr(self, '_configured_history_length'):
            if len(self.history) > self._configured_history_length:
                # Truncate to the configured length
                self.history.truncate(self._configured_history_length)
        
        return stop
    
    def _initialize_history(self, persistent_history_file=None):
        """
        Override cmd2's history initialization to respect our custom history limit
        and filter out excessively large history items.
        This is called during shell initialization.
        """
        import lzma
        import json
        from cmd2.history import History
        
        # Set our custom persistent history length before cmd2 loads history
        # This ensures cmd2 loads the full history up to our limit
        if hasattr(self, '_configured_history_length'):
            self._persistent_history_length = self._configured_history_length
        
        # Initialize empty history first
        self.history = History()
        
        # Maximum size for individual history items (1KB)
        MAX_HISTORY_ITEM_SIZE = 1024
        
        # Handle persistent history file ourselves to filter large items
        if persistent_history_file and self.is_interactive:
            hist_file = os.path.abspath(os.path.expanduser(persistent_history_file))
            self.persistent_history_file = hist_file
            
            # Check if file exists and is not a directory
            if os.path.exists(hist_file) and not os.path.isdir(hist_file):
                try:
                    # Read the compressed history file
                    with open(hist_file, 'rb') as fobj:
                        compressed_bytes = fobj.read()
                    
                    if compressed_bytes:
                        # Decompress
                        try:
                            history_json = lzma.decompress(compressed_bytes).decode(encoding='utf-8')
                            history_data = json.loads(history_json)
                            
                            # Filter history items by size
                            if isinstance(history_data, dict) and 'history_items' in history_data:
                                filtered_items = []
                                skipped_count = 0
                                
                                for item in history_data['history_items']:
                                    # Check the size of the raw command
                                    if isinstance(item, dict) and 'statement' in item:
                                        stmt = item['statement']
                                        if isinstance(stmt, dict) and 'raw' in stmt:
                                            raw_cmd = stmt['raw']
                                            if len(raw_cmd) <= MAX_HISTORY_ITEM_SIZE:
                                                filtered_items.append(item)
                                            else:
                                                skipped_count += 1
                                        else:
                                            # Keep items without 'raw' field
                                            filtered_items.append(item)
                                    else:
                                        # Keep items without proper structure
                                        filtered_items.append(item)
                                
                                # Recreate history with filtered items
                                if skipped_count > 0:
                                    self.poutput(f"{Fore.YELLOW}Note: Skipped {skipped_count} oversized history items{Style.RESET_ALL}")
                                
                                # Create new history data with filtered items
                                filtered_history_data = {
                                    'history_version': history_data.get('history_version', '1.0.0'),
                                    'history_items': filtered_items
                                }
                                
                                # Load the filtered history
                                filtered_json = json.dumps(filtered_history_data)
                                self.history = History.from_json(filtered_json)
                            else:
                                # Try to load as-is if structure is different
                                self.history = History.from_json(history_json)
                                
                        except (lzma.LZMAError, json.JSONDecodeError, KeyError, ValueError) as ex:
                            # If there's an error, start with empty history
                            self.poutput(f"{Fore.YELLOW}Warning: Could not load history: {ex}{Style.RESET_ALL}")
                            self.history = History()
                        
                except OSError as ex:
                    # Can't read file, start with empty history
                    self.poutput(f"{Fore.YELLOW}Warning: Cannot read history file: {ex}{Style.RESET_ALL}")
            
            # Register function to save history on exit
            import atexit
            atexit.register(self._persist_history)
            
            # Start a new session in history
            if hasattr(self.history, 'start_session'):
                self.history.start_session()
        else:
            # No persistent history file
            self.persistent_history_file = None
    
    def _persist_history(self) -> None:
        """
        Override cmd2's history persistence to respect our custom history limit.
        This is called when the shell exits.
        """
        import lzma
        if not self.persistent_history_file:
            return
        
        # Use our configured history length instead of cmd2's default
        history_length = getattr(self, '_configured_history_length', 1000)
        self.history.truncate(history_length)
        
        try:
            history_json = self.history.to_json()
            compressed_bytes = lzma.compress(history_json.encode(encoding='utf-8'))
            with open(self.persistent_history_file, 'wb') as fobj:
                fobj.write(compressed_bytes)
        except OSError as ex:
            self.perror(f"Cannot write persistent history file '{self.persistent_history_file}': {ex}")
    
    def complete_show(self, text: str, line: str, begidx: int, endidx: int) -> list:
        """Provide completion for show command - dynamically list all available variables."""
        # Get all available variables (both user and environment)
        all_vars = set()
        
        # Add user variables
        all_vars.update(self.variable_manager.variables.keys())
        
        # Add environment variables
        all_vars.update(os.environ.keys())
        
        # Return sorted list of variables that start with the typed text
        return sorted([var for var in all_vars if var.startswith(text)])
    
    def complete_unset(self, text: str, line: str, begidx: int, endidx: int) -> list:
        """Provide completion for unset command - only show user variables that can be unset."""
        # Only user variables can be unset (not environment variables)
        user_vars = self.variable_manager.variables.keys()
        
        # Return sorted list of variables that start with the typed text
        return sorted([var for var in user_vars if var.startswith(text)])

    print_parser = cmd2.Cmd2ArgumentParser()
    print_parser.add_argument('text', nargs='*', help='The text or variable to print')

    @cmd2.with_argparser(print_parser)
    def do_print(self, args):
        """
        Prints the given text. If the text is a valid JSON string,
        it will be pretty-printed with indentation.
        """
        output_str = ' '.join(args.text)
        try:
            # Attempt to parse the input string as JSON
            data = json.loads(output_str)
            # If successful, pretty-print it
            self.poutput(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            # If it's not a valid JSON string, print it as-is
            self.poutput(output_str)
    
    # Add the shell command
    shell_parser = cmd2.Cmd2ArgumentParser()
    shell_parser.add_argument('command', nargs='*', help='The command to execute in the system shell')

    @cmd2.with_argparser(shell_parser)
    def do_shell(self, args):
        """
        Execute a command in the system shell.
        Can be invoked as `shell ...` or `! ...`
        """
        command = ' '.join(args.command)
        if not command:
            self.poutput("Usage: ! <command>")
            return

        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.stdout:
                self.poutput(result.stdout)
            if result.stderr:
                self.poutput(f"{Fore.RED}Error: {result.stderr}{Style.RESET_ALL}")
        except subprocess.SubprocessError as e:
            self.poutput(f"{Fore.RED}Subprocess error executing shell command: {e}{Style.RESET_ALL}")
        except OSError as e:
            self.poutput(f"{Fore.RED}OS error executing shell command: {e}{Style.RESET_ALL}")
        except ValueError as e:
            self.poutput(f"{Fore.RED}Invalid arguments for shell command: {e}{Style.RESET_ALL}")

    # Alias '!' to 'shell'
    do_bang = do_shell

    def do_clear(self, args):
        """Clear the terminal screen (interactive mode only)."""
        if self.is_interactive:
            # Use ANSI escape sequences for cross-platform compatibility
            print('\033[2J\033[H', end='')
        else:
            # In non-interactive mode, ignore the command
            pass

    def default(self, statement: cmd2.Statement):
        """Called for any command not recognized."""
        # Check if it's a variable assignment first
        if self.variable_manager.process_command_for_assignment(statement.raw):
            # It was an assignment, manually add to history in interactive mode
            if self.is_interactive and hasattr(self, 'history'):
                # Create a HistoryItem and add it to history
                # HistoryItem needs a Statement object, and we already have one
                history_item = HistoryItem(statement)
                self.history.append(history_item)
            return

        # If not an assignment, check if it might be a variable name (interactive mode only)
        command = statement.command
        if self.is_interactive and command and command.isidentifier():
            # Check if it's a valid variable name
            if command in self.variable_manager.variables or command in os.environ:
                # It's a variable, show it using the show command
                self.do_show(f"-j {command}")
                return
            else:
                # Variable not found
                self.poutput(f"{Fore.RED}✗ Variable '{command}' not found{Style.RESET_ALL}")
                return

        # If not an assignment or variable, it's a true unknown command
        if self.is_interactive:
            self.poutput(f"{Fore.RED}✗ Unknown command: '{command}'{Style.RESET_ALL}")
            self.poutput(f"{Fore.YELLOW}ℹ Available commands:{Style.RESET_ALL}")
            self.do_help('')
        else:
            # In non-interactive mode, just print error and let quit_on_error handle exit
            sys.stderr.write(f"Error: Unknown command: '{command}'\n")

    def onecmd_plus_hooks(self, line: str, *, add_to_history: bool = True, **kwargs) -> bool:
        """Override to capture command output and return values."""
        import io
        import time
        from contextlib import redirect_stdout
        
        # Initialize return value
        self.variable_manager.set_variable('TSIM_RETURN_VALUE', '0')
        
        # Start timing the command execution
        start_time = time.time()
        
        # Check if this is a tsimsh command (not a variable assignment or shell command)
        if not self.variable_manager.process_command_for_assignment(line):
            # Parse the command to check if it's a known tsimsh command
            statement = self.statement_parser.parse(line)
            tsimsh_commands = ['network', 'trace', 'service', 'host', 'facts', 'print', 'variables', 'unset', 
                             'ping', 'mtr', 'completion', 'status', 'refresh', 'set', 'show']
            
            # Commands that should NOT have their output stored in TSIM_RESULT
            no_capture_commands = ['set', 'help', 'history', 'status', 'refresh', 'exit', 'quit', 'variables', 'print', 'show', 'unset']
            
            if statement.command in tsimsh_commands and statement.command not in no_capture_commands:
                # Check if JSON output is requested
                produces_json = '--json' in line or '-j' in line
                
                # Capture output for tsimsh commands
                output_buffer = io.StringIO()
                original_stdout = self.stdout
                
                try:
                    # Temporarily redirect stdout
                    self.stdout = output_buffer
                    # Call parent method with version compatibility
                    try:
                        # Try with add_to_history parameter (newer cmd2 versions)
                        result = super().onecmd_plus_hooks(line, add_to_history=add_to_history, **kwargs)
                    except TypeError:
                        # Fall back to without parameter (older cmd2 versions)
                        result = super().onecmd_plus_hooks(line)
                    
                    # Get the captured output
                    output = output_buffer.getvalue()
                    
                    # Handle JSON output specially
                    if produces_json and output:
                        try:
                            # Try to parse as JSON
                            import json
                            json_data = json.loads(output.strip())
                            self.variable_manager.set_variable('TSIM_RESULT', json_data)
                        except json.JSONDecodeError:
                            # Not valid JSON, store as string
                            self.variable_manager.set_variable('TSIM_RESULT', output.strip())
                    elif output:
                        # Non-JSON output
                        self.variable_manager.set_variable('TSIM_RESULT', output.strip())
                    
                    # Write output to original stdout
                    original_stdout.write(output)
                    
                    
                    # Calculate command duration and set TSIM_COMMAND_DURATION
                    duration_ms = int((time.time() - start_time) * 1000)
                    self.variable_manager.set_variable('TSIM_COMMAND_DURATION', str(duration_ms))
                    
                    # Never return True to exit shell (except for exit/quit commands)
                    if statement.command in ['exit', 'quit', 'EOF', 'eof']:
                        return result
                    return False
                    
                finally:
                    # Restore stdout
                    self.stdout = original_stdout
            else:
                # For non-tsimsh commands, execute normally
                try:
                    # Try with add_to_history parameter (newer cmd2 versions)
                    result = super().onecmd_plus_hooks(line, add_to_history=add_to_history, **kwargs)
                    # Calculate command duration and set TSIM_COMMAND_DURATION
                    duration_ms = int((time.time() - start_time) * 1000)
                    self.variable_manager.set_variable('TSIM_COMMAND_DURATION', str(duration_ms))
                    # Never exit shell unless it's exit/quit
                    return result if statement.command in ['exit', 'quit', 'EOF', 'eof'] else False
                except TypeError:
                    # Fall back to without parameter (older cmd2 versions)
                    result = super().onecmd_plus_hooks(line)
                    # Calculate command duration and set TSIM_COMMAND_DURATION
                    duration_ms = int((time.time() - start_time) * 1000)
                    self.variable_manager.set_variable('TSIM_COMMAND_DURATION', str(duration_ms))
                    return result if statement.command in ['exit', 'quit', 'EOF', 'eof'] else False
        
        # Variable assignment was already handled
        # Calculate command duration and set TSIM_COMMAND_DURATION
        duration_ms = int((time.time() - start_time) * 1000)
        self.variable_manager.set_variable('TSIM_COMMAND_DURATION', str(duration_ms))
        
        # Add to history if needed
        if add_to_history and self.is_interactive:
            # Create a Statement from the line and then a HistoryItem
            statement = self.statement_parser.parse(line)
            history_item = HistoryItem(statement)
            self.history.append(history_item)
            # Apply history length limit after adding
            if hasattr(self, '_configured_history_length') and len(self.history) > self._configured_history_length:
                self.history.truncate(self._configured_history_length)
        return False
    
    def precmd(self, statement: cmd2.Statement) -> cmd2.Statement:
        """
        This hook is called before the command is executed.
        It handles variable substitutions while preserving original command in history.
        """
        # statement.raw is the raw input line
        line = statement.raw
        
        # Skip variable substitution if variable_manager isn't ready yet
        # This can happen during initialization
        if not hasattr(self, 'variable_manager'):
            return super().precmd(statement)
            
        substituted_line = self.variable_manager.substitute_variables(line)
        
        # If no substitution occurred, just return the original statement
        if line == substituted_line:
            return super().precmd(statement)
        
        # Parse the substituted line to get the actual command to execute
        new_statement = self.statement_parser.parse(substituted_line)
        
        # IMPORTANT: To preserve the original command in history (not the substituted version),
        # we need to create a new Statement with the substituted content for execution
        # but keep the original raw field for history.
        
        try:
            # Use dataclasses.replace to create a modified copy while preserving the original raw
            import dataclasses
            
            # Create a new statement with substituted values for execution but original raw for history
            # This prevents memory issues when variables contain large values
            final_statement = dataclasses.replace(
                new_statement,
                raw=line  # Keep original command for history (e.g., "print $LARGE_VAR" not expanded)
            )
            
            return super().precmd(final_statement)
        except Exception:
            # If there's any issue with statement manipulation, just use the new statement as-is
            # This ensures the command still executes even if we can't preserve the original in history
            return super().precmd(new_statement)
    
    
    def do_EOF(self, line):
        """Handle Ctrl+D - exit shell."""
        if self.is_interactive:
            self.poutput(f"\n{Fore.CYAN}Goodbye!{Style.RESET_ALL}")
        return True
    
    # Also handle lowercase eof for compatibility
    do_eof = do_EOF
    
    def emptyline(self):
        """Called when an empty line is entered - do nothing instead of repeating last command."""
        pass
    
    
    def _initialize_handlers(self):
        """Initialize command handlers."""
        try:
            from .commands.facts import FactsCommands
            from .commands.network import NetworkCommands
            from .commands.host import HostCommands
            from .commands.service import ServiceCommands
            from .commands.completion import CompletionCommands
            from .commands.trace import TraceCommands
            from .commands.nettest import NetTestCommands
            
            self.facts_handler = FactsCommands(self)
            self.network_handler = NetworkCommands(self)
            self.host_handler = HostCommands(self)
            self.service_handler = ServiceCommands(self)
            self.completion_handler = CompletionCommands(self)
            self.trace_handler = TraceCommands(self)
            self.nettest_handler = NetTestCommands(self)

        except Exception as e:
            import traceback
            self.poutput(f"{Fore.RED}Error loading command handlers: {e}{Style.RESET_ALL}")
            if hasattr(self, 'verbose') and self.verbose:
                self.poutput(f"{Fore.YELLOW}Traceback:{Style.RESET_ALL}")
                self.poutput(traceback.format_exc())
            else:
                self.poutput(f"{Fore.YELLOW}Run tsimsh with -v for verbose error details{Style.RESET_ALL}")
            # Continue with basic shell functionality
        # Defer ksms_tester handler import until first use to avoid impacting startup
        self.ksms_tester_handler = None
    
    def _setup_completion(self):
        """Setup tab completion for commands."""
        if not self.is_interactive:
            return # No completion in batch mode
            
        try:
            from .completers.dynamic import DynamicCompleters
            self.completers = DynamicCompleters(self)
        except ImportError:
            # Continue without dynamic completion
            pass
    
    def _load_config(self):
        """Load configuration from file."""
        config_paths = [
            os.path.join(self.project_root, 'tsim_shell.yaml'),
            os.path.expanduser('~/.tsim_shell.yaml'),
            os.path.join(self.project_root, 'config.yaml')
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    import yaml
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                        self._apply_config(config)
                    break
                except ImportError:
                    # Continue without YAML config
                    pass
                except (FileNotFoundError, PermissionError) as e:
                    self.poutput(f"{Fore.YELLOW}Warning: Could not access config file {config_path}: {e}{Style.RESET_ALL}")
                except yaml.YAMLError as e:
                    self.poutput(f"{Fore.YELLOW}Warning: Invalid YAML in config file {config_path}: {e}{Style.RESET_ALL}")
                except (ValueError, TypeError) as e:
                    self.poutput(f"{Fore.YELLOW}Warning: Invalid config data in {config_path}: {e}{Style.RESET_ALL}")
    
    def _apply_config(self, config):
        """Apply configuration settings."""
        if 'shell' in config:
            shell_config = config['shell']
            if 'prompt' in shell_config:
                self.prompt = shell_config['prompt']
            if 'intro' in shell_config and self.is_interactive:
                self.intro = shell_config['intro']
    
    def _load_tsimrc(self):
        """Load and execute .tsimrc initialization file if it exists."""
        # Look for .tsimrc in current directory and home directory
        tsimrc_paths = [
            os.path.join(os.getcwd(), '.tsimrc'),
            os.path.expanduser('~/.tsimrc')
        ]
        
        for tsimrc_path in tsimrc_paths:
            if os.path.exists(tsimrc_path):
                try:
                    # Read the file
                    with open(tsimrc_path, 'r') as f:
                        lines = f.readlines()
                    
                    # Execute each line in the context of the shell
                    for line_num, line in enumerate(lines, 1):
                        line = line.strip()
                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            continue
                        
                        try:
                            # Execute the command but don't add to history
                            self.onecmd_plus_hooks(line, add_to_history=False)
                        except Exception as e:
                            if self.is_interactive:
                                self.poutput(f"{Fore.YELLOW}Warning: Error in {tsimrc_path} line {line_num}: {e}{Style.RESET_ALL}")
                    
                    # Only load the first .tsimrc found
                    break
                    
                except (FileNotFoundError, PermissionError) as e:
                    # Silently skip if can't read file
                    pass
                except Exception as e:
                    if self.is_interactive:
                        self.poutput(f"{Fore.YELLOW}Warning: Error loading {tsimrc_path}: {e}{Style.RESET_ALL}")
    
    def do_exit(self, _):
        """Exit the shell."""
        if self.is_interactive:
            self.poutput(f"{Fore.CYAN}Goodbye!{Style.RESET_ALL}")
        return True
    
    def do_quit(self, _):
        """Quit the shell."""
        return self.do_exit(_)
    
    def do_edit(self, args):
        """Edit command is disabled. Use ! <editor> <filename> instead."""
        self.poutput(f"{Fore.YELLOW}The 'edit' command has been disabled as it can hang in some environments.{Style.RESET_ALL}")
        self.poutput(f"{Fore.CYAN}Use the bang command instead:{Style.RESET_ALL}")
        self.poutput(f"  ! nano {args if args else '<filename>'}")
        self.poutput(f"  ! vim {args if args else '<filename>'}")
        self.poutput(f"  ! vi {args if args else '<filename>'}")
        return None
    
    # Create argument parsers with cmd2's Cmd2ArgumentParser
    def do_facts(self, args):
        """Manage routing facts collection and processing."""
        if hasattr(self, 'facts_handler'):
            ret = self.facts_handler.handle_command(args)
            # Set return value
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Facts commands not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_facts(self, text, line, begidx, endidx):
        """Provide completion for facts command."""
        if hasattr(self, 'facts_handler'):
            return self.facts_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_network(self, args):
        """Manage network namespace simulation."""
        if hasattr(self, 'network_handler'):
            ret = self.network_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Network commands not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_network(self, text, line, begidx, endidx):
        """Provide completion for network command."""
        if hasattr(self, 'network_handler'):
            return self.network_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_host(self, args):
        """Manage dynamic host creation and removal."""
        if hasattr(self, 'host_handler'):
            ret = self.host_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Host commands not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_host(self, text, line, begidx, endidx):
        """Provide completion for host command."""
        if hasattr(self, 'host_handler'):
            return self.host_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_service(self, args):
        """Manage TCP/UDP services in network simulation."""
        if hasattr(self, 'service_handler'):
            ret = self.service_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Service commands not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_service(self, text, line, begidx, endidx):
        """Provide completion for service command."""
        if hasattr(self, 'service_handler'):
            return self.service_handler.complete_command(text, line, begidx, endidx)
        return []

    def do_ksms_tester(self, args):
        """Kernel-space multi-service tester (fast YES/NO per router)."""
        try:
            if self.ksms_tester_handler is None:
                from .commands.ksms_tester import KsmsTesterCommand
                self.ksms_tester_handler = KsmsTesterCommand(self)
            ret = self.ksms_tester_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None
        except Exception as e:
            self.poutput(f"{Fore.RED}ksms_tester command not available: {e}{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None

    def complete_ksms_tester(self, text, line, begidx, endidx):
        try:
            if self.ksms_tester_handler is None:
                from .commands.ksms_tester import KsmsTesterCommand
                self.ksms_tester_handler = KsmsTesterCommand(self)
            return self.ksms_tester_handler.complete_command(text, line, begidx, endidx)
        except Exception:
            return []
    
    
    def do_completion(self, args):
        """Generate shell completion scripts."""
        if hasattr(self, 'completion_handler'):
            ret = self.completion_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Completion commands not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_completion(self, text, line, begidx, endidx):
        """Provide completion for completion command."""
        if hasattr(self, 'completion_handler'):
            return self.completion_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_trace(self, args):
        """Perform reverse path tracing between source and destination."""
        if hasattr(self, 'trace_handler'):
            ret = self.trace_handler.handle_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Trace command not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_trace(self, text, line, begidx, endidx):
        """Provide completion for trace command."""
        if hasattr(self, 'trace_handler'):
            return self.trace_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_ping(self, args):
        """Test connectivity between IPs using ping."""
        if hasattr(self, 'nettest_handler'):
            ret = self.nettest_handler.handle_ping_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Ping command not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_ping(self, text, line, begidx, endidx):
        """Provide completion for ping command."""
        if hasattr(self, 'nettest_handler'):
            return self.nettest_handler.complete_ping_command(text, line, begidx, endidx)
        return []
    
    def do_mtr(self, args):
        """Test connectivity between IPs using MTR (My TraceRoute)."""
        if hasattr(self, 'nettest_handler'):
            ret = self.nettest_handler.handle_mtr_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}MTR command not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_mtr(self, text, line, begidx, endidx):
        """Provide completion for mtr command."""
        if hasattr(self, 'nettest_handler'):
            return self.nettest_handler.complete_mtr_command(text, line, begidx, endidx)
        return []
    
    def do_traceroute(self, args):
        """Test connectivity between IPs using traceroute."""
        if hasattr(self, 'nettest_handler'):
            ret = self.nettest_handler.handle_traceroute_command(args)
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', str(ret if ret is not None else 0))
            return None  # Never exit shell
        else:
            self.poutput(f"{Fore.RED}Traceroute command not available{Style.RESET_ALL}")
            self.variable_manager.set_variable('TSIM_RETURN_VALUE', '1')
            return None
    
    def complete_traceroute(self, text, line, begidx, endidx):
        """Provide completion for traceroute command."""
        if hasattr(self, 'nettest_handler'):
            return self.nettest_handler.complete_traceroute_command(text, line, begidx, endidx)
        return []
    
    def complete_shell(self, text, line, begidx, endidx):
        """Provide file completion for shell command."""
        import glob
        import os
        
        # Get the partial path being typed
        args = line.split()
        if len(args) > 1:
            # Check if we're completing a file path
            partial_path = text
            
            # Handle paths with directories
            if '/' in partial_path:
                dir_path = os.path.dirname(partial_path)
                base_name = os.path.basename(partial_path)
                if os.path.isdir(dir_path):
                    files = glob.glob(os.path.join(dir_path, base_name + '*'))
                    return [f for f in files]
            else:
                # Complete files in current directory
                files = glob.glob(partial_path + '*')
                return files
        
        # If it's the first argument after 'shell' or '!', suggest common commands
        common_cmds = ['ls', 'cat', 'grep', 'find', 'cd', 'pwd', 'echo', 'python3', 'make']
        return [cmd for cmd in common_cmds if cmd.startswith(text)]
    
    def complete_print(self, text, line, begidx, endidx):
        """Provide variable completion for print command."""
        # Get all shell variables for completion
        if hasattr(self, 'variable_manager') and self.variable_manager.variables:
            # Extract variable names and format them with $
            var_names = [f'${var}' for var in self.variable_manager.variables.keys()]
            return [var for var in var_names if var.startswith(text)]
        return []
    
    def do_status(self, args):
        """Show current shell status and configuration."""
        self.poutput(f"{Fore.CYAN}Traceroute Simulator Shell Status{Style.RESET_ALL}")
        self.poutput(f"Project root: {self.project_root}")
        self.poutput(f"Facts directory: {self.facts_dir}")
        
        # Check if handlers are available
        handlers = [
            ('Facts', hasattr(self, 'facts_handler')),
            ('Network', hasattr(self, 'network_handler')),
            ('Host', hasattr(self, 'host_handler')),
            ('Service', hasattr(self, 'service_handler')),
            ('Trace', hasattr(self, 'trace_handler')),
            ('NetTest', hasattr(self, 'nettest_handler')),
            ('Completion', hasattr(self, 'completion_handler'))
        ]
        
        self.poutput("\nCommand handlers:")
        for name, available in handlers:
            status = f"{Fore.GREEN}✓{Style.RESET_ALL}" if available else f"{Fore.RED}✗{Style.RESET_ALL}"
            self.poutput(f"  {status} {name}")
        
        # Show completion status
        if hasattr(self, 'completers'):
            self.poutput(f"\nCompletion cache:")
            router_count = len(self.completers._get_router_names()) if self.completers._cached_routers else 0
            ip_count = len(self.completers._get_all_ips()) if self.completers._cached_ips else 0
            self.poutput(f"  Routers: {router_count} cached")
            self.poutput(f"  IPs: {ip_count} cached")
    
    def do_refresh(self, _):
        """Refresh completion cache and reload facts."""
        self.poutput(f"{Fore.CYAN}Refreshing completion cache...{Style.RESET_ALL}")
        
        if hasattr(self, 'completers'):
            self.completers.clear_cache()
            # Pre-load the cache
            router_count = len(self.completers._get_router_names())
            ip_count = len(self.completers._get_all_ips())
            self.poutput(f"{Fore.GREEN}✓{Style.RESET_ALL} Loaded {router_count} routers and {ip_count} IPs")
        else:
            self.poutput(f"{Fore.RED}✗{Style.RESET_ALL} No completion system available")
    
    def do_help(self, args):
        """Show help information."""
        # Handle the case where args might be a list or string
        if isinstance(args, list):
            # If it's a list, join it to get the command name
            command_name = ' '.join(args) if args else ''
        else:
            # If it's a string, use it directly
            command_name = str(args).strip() if args else ''
        
        if command_name:
            # Check if it's one of our custom commands
            custom_commands = {
                'facts': self.help_facts,
                'network': self.help_network,
                'host': self.help_host,
                'service': self.help_service,
                'trace': self.help_trace,
                'ping': self.help_ping,
                'mtr': self.help_mtr,
                'traceroute': self.help_traceroute,
                'ksms_tester': self.help_ksms_tester,
                'completion': self.help_completion
            }
            
            if command_name in custom_commands:
                custom_commands[command_name]()
            else:
                super().do_help(args)
        else:
            super().do_help(args)
    
    def do_history(self, args):
        """Show command history - uses cmd2's built-in history with TSIM_HISTORY_LENGTH limit."""
        # Get configured history length
        history_length_str = self.variable_manager.get_variable('TSIM_HISTORY_LENGTH')
        try:
            max_history = int(history_length_str) if history_length_str else 1000
        except ValueError:
            max_history = 1000
        
        # Use cmd2's built-in history command but respect our limit
        # cmd2 stores history in self.history
        if hasattr(self, 'history') and self.history:
            # Get the history items
            history_items = list(self.history)
            
            # Apply our configured limit
            if len(history_items) > max_history:
                history_items = history_items[-max_history:]
                self.poutput(f"{Fore.CYAN}Command History (last {max_history} entries):{Style.RESET_ALL}")
            else:
                self.poutput(f"{Fore.CYAN}Command History:{Style.RESET_ALL}")
            
            # Display history with line numbers
            for i, item in enumerate(history_items, 1):
                # Format: line_number: command
                self.poutput(f"{i:5d}: {item}")
        else:
            # Fall back to parent's history command
            super().do_history(args)
    
    def help_facts(self):
        """Comprehensive help for facts command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  facts - Manage routing facts collection and processing")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  facts collect [options]")
        self.poutput("  facts process [options]") 
        self.poutput("  facts validate [options]")
        self.poutput("  facts --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}SUBCOMMANDS:{Style.RESET_ALL}")
        self.poutput("  collect   - Collect routing facts from network devices")
        self.poutput("  process   - Process raw facts into structured JSON")
        self.poutput("  validate  - Validate processed facts files")
        
        self.poutput(f"\n{Fore.CYAN}COLLECT OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}--inventory FILE{Style.RESET_ALL}     Ansible inventory file (MANDATORY)")
        self.poutput("  --output-dir DIR      Output directory for facts (default: facts)")
        self.poutput("  --test                Use test data instead of real collection")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}PROCESS OPTIONS:{Style.RESET_ALL}")
        self.poutput("  --input-dir DIR       Input directory with raw facts")
        self.poutput("  --output-dir DIR      Output directory for JSON files")
        self.poutput("  --create-dirs         Create output directories if missing")
        self.poutput("  --validate            Validate JSON after processing")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}VALIDATE OPTIONS:{Style.RESET_ALL}")
        self.poutput("  --facts-dir DIR       Facts directory to validate")
        self.poutput("  -v, --verbose         Show detailed validation results")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Collect facts from production:")
        self.poutput("    facts collect --inventory hosts.ini --output-dir prod_facts")
        self.poutput("\n  Process raw facts with validation:")
        self.poutput("    facts process --input-dir raw_facts --output-dir json_facts --validate")
        self.poutput("\n  Validate existing facts:")
        self.poutput("    facts validate --facts-dir json_facts --verbose")
        self.poutput("")
    
    def help_network(self):
        """Comprehensive help for network command."""
        self.poutput("\nCOMMAND:")
        self.poutput("  network - Manage network namespace simulation")
        
        self.poutput("\nUSAGE:")
        self.poutput("  network setup [options]           # Fast batch mode")
        self.poutput("  network setup-serial [options]    # Slow serial mode")
        self.poutput("  network status [function] [options]")
        self.poutput("  network clean [options]           # Fast batch mode")
        self.poutput("  network clean-serial [options]    # Slow serial mode")
        self.poutput("  network test [options]")
        self.poutput("  network --help | -h")
        
        self.poutput("\nSUBCOMMANDS:")
        self.poutput("  setup         - Setup network namespace simulation (batch mode)")
        self.poutput("  setup-serial  - Setup network namespace simulation (serial mode)")
        self.poutput("  status        - Show network namespace status")
        self.poutput("  clean         - Clean up network namespaces (batch mode)")
        self.poutput("  clean-serial  - Clean up network namespaces (serial mode)")
        self.poutput("  test          - Test network connectivity")
        
        self.poutput("\nSETUP OPTIONS (batch mode):")
        self.poutput("  --create              Create the network setup")
        self.poutput("  --clean               Clean existing setup")
        self.poutput("  --verify              Verify network setup")
        self.poutput("  --keep-batch-files    Keep batch files for debugging")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nSETUP-SERIAL OPTIONS:")
        self.poutput("  --limit PATTERN       Limit to specific namespaces (glob pattern)")
        self.poutput("  --verify              Verify setup after creation")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nSTATUS OPTIONS:")
        self.poutput("  function              What to display: interfaces, routes, rules, iptables, ipsets, all, summary")
        self.poutput("  --limit PATTERN       Limit to specific namespaces (glob pattern)")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nCLEAN OPTIONS (batch mode):")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nCLEAN-SERIAL OPTIONS:")
        self.poutput("  --force               Force cleanup without confirmation")
        self.poutput("  --limit PATTERN       Limit to specific namespaces (glob pattern)")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nTEST OPTIONS:")
        self.poutput("  --source IP           Source IP address (MANDATORY)")
        self.poutput("  --destination IP      Destination IP address (MANDATORY)")
        self.poutput("  --all                 Test all paths")
        self.poutput("  --test-type TYPE      Test type: ping, mtr")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput("\nEXAMPLES:")
        self.poutput("\n  Setup network simulation (batch mode):")
        self.poutput("    network setup --create")
        self.poutput("    network setup --clean --create")
        self.poutput("    network setup --clean --create --verify")
        
        self.poutput("\n  Verify existing setup:")
        self.poutput("    network setup --verify")
        
        self.poutput("\n  Setup network simulation (serial mode):")
        self.poutput("    network setup-serial")
        
        self.poutput("\n  Show status of all namespaces:")
        self.poutput("    network status")
        
        self.poutput("\n  Show interfaces for specific router:")
        self.poutput("    network status interfaces --limit hq-*")
        
        self.poutput("\n  Test connectivity:")
        self.poutput("    network test --source 10.1.1.1 --destination 10.2.1.1")
        
        self.poutput("\n  Clean up all namespaces:")
        self.poutput("    network clean --force")
        self.poutput("")
    
    def help_host(self):
        """Comprehensive help for host command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  host - Manage dynamic host creation and removal")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  host add --name NAME --primary-ip IP/MASK --connect-to ROUTER [options]")
        self.poutput("  host list [options]")
        self.poutput("  host remove --name NAME [options]")
        self.poutput("  host clean [options]")
        self.poutput("  host --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}SUBCOMMANDS:{Style.RESET_ALL}")
        self.poutput("  add     - Add a new host to the network")
        self.poutput("  list    - List all hosts")
        self.poutput("  remove  - Remove a host from the network")
        self.poutput("  clean   - Remove all hosts")
        
        self.poutput(f"\n{Fore.CYAN}ADD OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}--name NAME{Style.RESET_ALL}          Host name (MANDATORY)")
        self.poutput(f"  {Fore.YELLOW}--primary-ip IP/MASK{Style.RESET_ALL} Primary IP with CIDR (MANDATORY)")
        self.poutput(f"  {Fore.YELLOW}--connect-to ROUTER{Style.RESET_ALL}  Router to connect to (MANDATORY)")
        self.poutput("  --secondary-ips IPS   Secondary IP addresses")
        self.poutput("  --no-delay            Skip stabilization delays for faster creation")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}LIST OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}REMOVE OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}--name NAME{Style.RESET_ALL}          Host name to remove (MANDATORY)")
        self.poutput("  -f, --force           Force removal without confirmation")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}CLEAN OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -f, --force           Force cleanup without confirmation")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Add a host:")
        self.poutput("    host add --name web1 --primary-ip 10.1.1.100/24 --connect-to hq-gw")
        
        self.poutput("\n  Add host with secondary IPs:")
        self.poutput("    host add --name db1 --primary-ip 10.3.20.100/24 --connect-to dc-srv --secondary-ips 192.168.1.1/24")
        
        self.poutput("\n  List all hosts:")
        self.poutput("    host list")
        
        self.poutput("\n  Remove a host:")
        self.poutput("    host remove --name web1 -f")
        
        self.poutput("\n  Clean all hosts:")
        self.poutput("    host clean -f")
        self.poutput("")
    
    def help_service(self):
        """Comprehensive help for service command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  service - Manage TCP/UDP services in network simulation")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  service start --ip IP --port PORT [options]")
        self.poutput("  service test -s SOURCE_IP -d DEST_IP:PORT [options]")
        self.poutput("  service list [options]")
        self.poutput("  service stop --ip IP --port PORT [options]")
        self.poutput("  service clean [options]")
        self.poutput("  service --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}SUBCOMMANDS:{Style.RESET_ALL}")
        self.poutput("  start   - Start a TCP/UDP service")
        self.poutput("  test    - Test service connectivity")
        self.poutput("  list    - List all active services")
        self.poutput("  stop    - Stop a service")
        self.poutput("  clean   - Stop all services")
        
        self.poutput(f"\n{Fore.CYAN}START OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}--ip IP{Style.RESET_ALL}              IP address to bind to (MANDATORY)")
        self.poutput(f"  {Fore.YELLOW}--port PORT{Style.RESET_ALL}          Port number (MANDATORY)")
        self.poutput("  -p, --protocol PROTO  Protocol: tcp, udp (default: tcp)")
        self.poutput("  --name NAME           Service name")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}TEST OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}-s, --source IP{Style.RESET_ALL}      Source IP address (MANDATORY)")
        self.poutput(f"  {Fore.YELLOW}-d, --destination IP:PORT{Style.RESET_ALL}   Destination IP:PORT (MANDATORY)")
        self.poutput("  -p, --protocol PROTO  Protocol: tcp, udp (default: tcp)")
        self.poutput("  -m, --message MSG     Message to send")
        self.poutput("  --timeout SECONDS     Timeout in seconds (default: 5)")
        self.poutput("  -v, --verbose         Increase verbosity (-v, -vv, -vvv)")
        self.poutput("  -j, --json            Output in JSON format")
        
        self.poutput(f"\n{Fore.CYAN}LIST OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}STOP OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}--ip IP{Style.RESET_ALL}              Service IP address (MANDATORY)")
        self.poutput(f"  {Fore.YELLOW}--port PORT{Style.RESET_ALL}          Service port (MANDATORY)")
        self.poutput("  -p, --protocol PROTO  Protocol: tcp, udp (default: tcp)")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}CLEAN OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -f, --force           Force cleanup without confirmation")
        self.poutput("  -v, --verbose         Increase verbosity")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Start a TCP service:")
        self.poutput("    service start --ip 10.1.1.1 --port 8080 --name webserver")
        
        self.poutput("\n  Start a UDP service:")
        self.poutput("    service start --ip 10.2.1.1 --port 53 -p udp --name dns")
        
        self.poutput("\n  Test TCP connectivity:")
        self.poutput("    service test -s 10.1.1.100 -d 10.1.1.1:8080")
        
        self.poutput("\n  Test UDP with message:")
        self.poutput("    service test -s 10.1.1.100 -d 10.2.1.1:53 -p udp -m 'DNS Query'")
        
        self.poutput("\n  List services as JSON:")
        self.poutput("    service list -j")
        
        self.poutput("\n  Stop a service:")
        self.poutput("    service stop --ip 10.1.1.1 --port 8080")
        self.poutput("")
    
    
    def help_completion(self):
        """Help for completion command."""
        self.poutput(f"{Fore.CYAN}Completion Commands:{Style.RESET_ALL}")
        self.poutput("  completion generate --shell SHELL [--output-file FILE]")
        self.poutput("    Generate completion script for bash/zsh/fish")
        self.poutput("  completion install --shell SHELL [--global]")
        self.poutput("    Install completion script")
        self.poutput("  completion uninstall --shell SHELL [--global]")
        self.poutput("    Uninstall completion script")
        self.poutput("")
        self.poutput(f"{Fore.CYAN}Completion Rebuild Options:{Style.RESET_ALL}")
        self.poutput("┌─────────────────────┬─────────────────────┬─────────────────────────────────────┐")
        self.poutput("│ Method              │ When to Use         │ Command                             │")
        self.poutput("├─────────────────────┼─────────────────────┼─────────────────────────────────────┤")
        self.poutput("│ refresh             │ After facts change  │ ./tsimsh then refresh               │")
        self.poutput("│ status              │ Check current state │ ./tsimsh then status                │")
        self.poutput("│ completion generate │ Rebuild ext scripts │ completion generate --shell bash    │")
        self.poutput("│ completion install  │ Install to shell    │ completion install --shell bash     │")
        self.poutput("│ restart tsimsh      │ After code changes  │ Exit and restart ./tsimsh           │")
        self.poutput("│ Change environment  │ New facts directory │ export TRACEROUTE_SIMULATOR_FACTS=… │")
        self.poutput("└─────────────────────┴─────────────────────┴─────────────────────────────────────┘")
    
    def help_trace(self):
        """Comprehensive help for trace command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  trace - Perform reverse path tracing between source and destination")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  trace -s SOURCE_IP -d DESTINATION_IP [options]")
        self.poutput("  trace --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}MANDATORY OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}-s, --source IP{Style.RESET_ALL}      Source IP address")
        self.poutput(f"  {Fore.YELLOW}-d, --destination IP{Style.RESET_ALL} Destination IP address")
        
        self.poutput(f"\n{Fore.CYAN}OPTIONAL OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity (can be used multiple times)")
        self.poutput("  --controller-ip IP    Ansible controller IP (auto-detected if not provided)")
        self.poutput("  -h, --help            Show this help message")
        
        self.poutput(f"\n{Fore.CYAN}OUTPUT FORMATS:{Style.RESET_ALL}")
        self.poutput("  Default: Human-readable text format showing hop-by-hop path")
        self.poutput("  JSON: Machine-readable format with detailed hop information")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Basic path trace:")
        self.poutput("    trace -s 10.1.1.100 -d 10.2.1.200")
        
        self.poutput("\n  JSON output for scripting:")
        self.poutput("    trace -s 10.1.1.100 -d 10.2.1.200 -j")
        
        self.poutput("\n  Verbose output with timing:")
        self.poutput("    trace -s 10.1.1.100 -d 10.2.1.200 -vv")
        
    def help_ksms_tester(self):
        """Help for ksms_tester command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  ksms_tester - Kernel-space multi-service tester (fast YES/NO per router)")

        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s SOURCE_IP -d DESTINATION_IP -P \"PORT_SPEC\" [options]")
        self.poutput("  ksms_tester --help | -h")

        self.poutput(f"\n{Fore.CYAN}MANDATORY OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}-s, --source IP{Style.RESET_ALL}           Source IP address")
        self.poutput(f"  {Fore.YELLOW}-d, --destination IP{Style.RESET_ALL}      Destination IP address")
        self.poutput(f"  {Fore.YELLOW}-P, --ports SPEC{Style.RESET_ALL}         Port spec (e.g., 80,443/tcp,1000-2000/udp,22-25)")

        self.poutput(f"\n{Fore.CYAN}OPTIONAL OPTIONS:{Style.RESET_ALL}")
        self.poutput("  --default-proto PROTO       Default protocol for bare ports: tcp|udp (default: tcp)")
        self.poutput("  --max-services N            Max services to expand (default: 10)")
        self.poutput("  --range-limit N             Max ports per range (default: 100, max: 65535)")
        self.poutput("  --tcp-timeout SEC           TCP SYN timeout per service (default: 1.0)")
        self.poutput("  --force                     Force large ranges without confirmation")
        self.poutput("  -j, --json                  Output in JSON format")
        self.poutput("  -v, --verbose               Increase verbosity (-v, -vv, -vvv)")

        self.poutput(f"\n{Fore.CYAN}DESCRIPTION:{Style.RESET_ALL}")
        self.poutput("  Tests service reachability using kernel-space packet counters. Emits DSCP-marked probes")
        self.poutput("  (TCP SYN or UDP packets) and analyzes PREROUTING/POSTROUTING counter deltas on routers.")
        self.poutput("  Results: YES (forwarded), NO (blocked), UNKNOWN (no packets seen).")
        self.poutput("  Routers are automatically inferred from source IP using network registries.")

        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.GREEN}# Test single port{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80\"")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Test multiple TCP ports with verbose output{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80,443,8080\" -v")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Test UDP services{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"53,123\" --default-proto udp")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Test mixed protocols{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80/tcp,53/udp,443/tcp\"")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Test port ranges{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"8000-8005/tcp,1000-1010/udp\"")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# JSON output for automation{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80,443\" -j")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Maximum verbosity for debugging{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80\" -vvv")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Large port range with custom limit and force{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"1000-2000/tcp\" --range-limit 1001 --force")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Advanced: Test 1000+ TCP ports (fast with parallel probes){Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"1000-2000/tcp\" --max-services 2000 --force")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Advanced: Test 1000+ UDP ports (burst control prevents packet loss){Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"1000-2000/udp\" --max-services 2000 --force")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Performance: Fast timeout for blocked services{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"1-1000/tcp\" --tcp-timeout 0.1 --force")
        self.poutput("")
        self.poutput(f"  {Fore.GREEN}# Production: Large-scale mixed protocol testing with JSON output{Style.RESET_ALL}")
        self.poutput("  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P \"80-90/tcp,1000-1100/udp,443,53/udp\" --max-services 200 --force -j")
        self.poutput("")
        
        self.poutput(f"\n{Fore.CYAN}PERFORMANCE NOTES:{Style.RESET_ALL}")
        self.poutput("  • TCP services: Parallel execution (~1000 ports in ~1-2 seconds)")
        self.poutput("  • UDP services: Burst control with batching to prevent packet loss")
        self.poutput("  • DSCP cycling: Supports unlimited services (cycles through 32-63)")
        self.poutput("  • Interactive confirmation: Large ranges prompt for user approval")
        self.poutput("")
        
        self.poutput(f"\n{Fore.CYAN}PORT SPECIFICATION FORMATS:{Style.RESET_ALL}")
        self.poutput("  80              Single port with default protocol")
        self.poutput("  80/tcp          Single port with specific protocol")
        self.poutput("  80,443,8080     Multiple ports (comma-separated)")
        self.poutput("  80/tcp,53/udp   Mixed protocols")
        self.poutput("  1000-2000/tcp   Port range with protocol")
        self.poutput("  1000-2000       Port range with default protocol")
        self.poutput("  Complex: \"80/tcp,53/udp,443,1000-1100/tcp,2000-3000/udp\"")
        self.poutput("")
    
    def help_ping(self):
        """Comprehensive help for ping command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  ping - Test connectivity between IPs using ping")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  ping -s SOURCE_IP -d DESTINATION_IP [options]")
        self.poutput("  ping --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}MANDATORY OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}-s, --source IP{Style.RESET_ALL}      Source IP address")
        self.poutput(f"  {Fore.YELLOW}-d, --destination IP{Style.RESET_ALL} Destination IP address")
        
        self.poutput(f"\n{Fore.CYAN}OPTIONAL OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity (can be used multiple times)")
        self.poutput("  -h, --help            Show this help message")
        
        self.poutput(f"\n{Fore.CYAN}DESCRIPTION:{Style.RESET_ALL}")
        self.poutput("  Tests connectivity from all namespaces containing the source IP")
        self.poutput("  to all namespaces containing the destination IP. Shows ping results")
        self.poutput("  and routing paths for successful connections.")
        self.poutput("")
        self.poutput("  When using -j/--json, the output is structured JSON with summary")
        self.poutput("  statistics and detailed test results.")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Basic connectivity test:")
        self.poutput("    ping -s 10.1.1.100 -d 10.2.1.200")
        
        self.poutput("\n  Verbose output with details:")
        self.poutput("    ping -s 10.1.1.100 -d 10.2.1.200 -vv")
        
        self.poutput("\n  JSON output for scripting:")
        self.poutput("    ping -s 10.1.1.100 -d 10.2.1.200 -j")
        self.poutput("    # Result stored in $TSIM_RESULT as JSON")
        
        self.poutput("\n  Check return value:")
        self.poutput("    ping -s 10.1.1.100 -d 10.2.1.200")
        self.poutput("    echo $TSIM_RETURN_VALUE")
        self.poutput("")
    
    def help_mtr(self):
        """Comprehensive help for mtr command."""
        self.poutput(f"\n{Fore.CYAN}COMMAND:{Style.RESET_ALL}")
        self.poutput("  mtr - Test connectivity between IPs using MTR (My TraceRoute)")
        
        self.poutput(f"\n{Fore.CYAN}USAGE:{Style.RESET_ALL}")
        self.poutput("  mtr -s SOURCE_IP -d DESTINATION_IP [options]")
        self.poutput("  mtr --help | -h")
        
        self.poutput(f"\n{Fore.CYAN}MANDATORY OPTIONS:{Style.RESET_ALL}")
        self.poutput(f"  {Fore.YELLOW}-s, --source IP{Style.RESET_ALL}      Source IP address")
        self.poutput(f"  {Fore.YELLOW}-d, --destination IP{Style.RESET_ALL} Destination IP address")
        
        self.poutput(f"\n{Fore.CYAN}OPTIONAL OPTIONS:{Style.RESET_ALL}")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity (can be used multiple times)")
        self.poutput("  -h, --help            Show this help message")
        
        self.poutput(f"\n{Fore.CYAN}DESCRIPTION:{Style.RESET_ALL}")
        self.poutput("  Tests connectivity from all namespaces containing the source IP")
        self.poutput("  to all namespaces containing the destination IP. Uses MTR to show")
        self.poutput("  hop-by-hop path and latency information for successful connections.")
        self.poutput("")
        self.poutput("  When using -j/--json, the output is structured JSON with summary")
        self.poutput("  statistics and detailed test results.")
        
        self.poutput(f"\n{Fore.CYAN}EXAMPLES:{Style.RESET_ALL}")
        self.poutput("\n  Basic MTR trace:")
        self.poutput("    mtr -s 10.1.1.100 -d 10.2.1.200")
        
        self.poutput("\n  Verbose output with details:")
        self.poutput("    mtr -s 10.1.1.100 -d 10.2.1.200 -vv")
        
        self.poutput("\n  JSON output for scripting:")
        self.poutput("    mtr -s 10.1.1.100 -d 10.2.1.200 -j")
        self.poutput("    # Result stored in $TSIM_RESULT as JSON")
        
        self.poutput("\n  Check return value:")
        self.poutput("    mtr -s 10.1.1.100 -d 10.2.1.200")
        self.poutput("    echo $TSIM_RETURN_VALUE")
        self.poutput("")
    
    def help_traceroute(self):
        """Comprehensive help for traceroute command."""
        self.poutput("\nCOMMAND:")
        self.poutput("  traceroute - Test connectivity between IPs using traceroute")
        
        self.poutput("\nUSAGE:")
        self.poutput("  traceroute -s SOURCE_IP -d DESTINATION_IP [options]")
        self.poutput("  traceroute --help | -h")
        
        self.poutput("\nMANDATORY OPTIONS:")
        self.poutput("  -s, --source IP      Source IP address")
        self.poutput("  -d, --destination IP Destination IP address")
        
        self.poutput("\nOPTIONAL OPTIONS:")
        self.poutput("  -j, --json            Output in JSON format")
        self.poutput("  -v, --verbose         Increase verbosity (can be used multiple times)")
        self.poutput("  -h, --help            Show this help message")
        
        self.poutput("\nDESCRIPTION:")
        self.poutput("  Tests connectivity from all namespaces containing the source IP")
        self.poutput("  to all namespaces containing the destination IP. Uses traceroute to show")
        self.poutput("  hop-by-hop path and latency information for successful connections.")
        self.poutput("")
        self.poutput("  When using -j/--json, the output is structured JSON with summary")
        self.poutput("  statistics and detailed test results.")
        
        self.poutput("\nEXAMPLES:")
        self.poutput("\n  Basic traceroute:")
        self.poutput("    traceroute -s 10.1.1.100 -d 10.2.1.200")
        
        self.poutput("\n  Verbose output with details:")
        self.poutput("    traceroute -s 10.1.1.100 -d 10.2.1.200 -vv")
        
        self.poutput("\n  JSON output for scripting:")
        self.poutput("    traceroute -s 10.1.1.100 -d 10.2.1.200 -j")
        self.poutput("    # Result stored in $TSIM_RESULT as JSON")
        
        self.poutput("\n  Check return value:")
        self.poutput("    traceroute -s 10.1.1.100 -d 10.2.1.200")
        self.poutput("    echo $TSIM_RETURN_VALUE")
        self.poutput("")



def main():
    """Main entry point for running the shell standalone."""
    import sys
    
    try:
        # Create shell instance
        shell = TracerouteSimulatorShell()
        
        # Check if we're in batch mode (input or output is not a terminal)
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            from .utils.script_processor import ScriptProcessor
            # Read all input
            script_lines = sys.stdin.readlines()
            
            # Process script with control flow support
            processor = ScriptProcessor(shell.variable_manager, shell)
            exit_code = processor.process_script(script_lines)
            sys.exit(exit_code)
        else:
            # Interactive mode
            shell.cmdloop()
            
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)
    except ImportError as e:
        print(f"Error importing shell modules: {e}")
        print("Make sure all dependencies are installed: pip install tsim")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

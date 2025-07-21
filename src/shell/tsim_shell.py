
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


class TracerouteSimulatorShell(cmd2.Cmd):
    """Interactive shell for traceroute simulator operations."""
    
    # Class attribute for cmd2 compatibility
    orig_rl_history_length = 0
    
    def __init__(self, *args, **kwargs):
        # Detect if we are in an interactive session
        self.is_interactive = sys.stdin.isatty()

        # Configure persistent history before calling super().__init__
        history_file = os.path.expanduser('~/.tsimsh_history.json')
        kwargs['persistent_history_file'] = history_file
        
        # Simple prompt
        self.base_prompt = f"{Fore.GREEN}tsimsh{Style.RESET_ALL}"
        
        # Work around for cmd2 version compatibility issue with orig_rl_history_length
        # This attribute is referenced in some versions of cmd2 but not initialized in others
        # Setting it to 0 prevents AttributeError when cmd2 tries to access it
        # Set this BEFORE calling super().__init__()
        self.orig_rl_history_length = 0
        
        super().__init__(*args, **kwargs)
        
        # Initialize the VariableManager
        self.variable_manager = VariableManager(self)
        
        # --- Mode-specific configuration ---
        if self.is_interactive:
            # Shell configuration for interactive mode
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

    def do_set(self, _):
        """Display all currently set shell variables."""
        self.poutput(f"{Fore.CYAN}--- Shell Variables ---{Style.RESET_ALL}")
        if not self.variable_manager.variables:
            self.poutput("No variables set.")
            return

        for key, value in self.variable_manager.variables.items():
            if isinstance(value, dict):
                val_str = f"dictionary with {len(value)} keys"
            elif isinstance(value, list):
                val_str = f"list with {len(value)} items"
            else:
                val_str = f'"{value}"'
            self.poutput(f"  {Fore.GREEN}{key}{Style.RESET_ALL} = {val_str}")

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

    def default(self, statement: cmd2.Statement):
        """Called for any command not recognized."""
        # Check if it's a variable assignment first
        if self.variable_manager.process_command_for_assignment(statement.raw):
            # It was an assignment, so we do nothing.
            return

        # If not an assignment, it's a true unknown command
        command = statement.command
        if self.is_interactive:
            self.poutput(f"{Fore.RED}✗ Unknown command: '{command}'{Style.RESET_ALL}")
            self.poutput(f"{Fore.YELLOW}ℹ Available commands:{Style.RESET_ALL}")
            self.do_help('')
        else:
            # In non-interactive mode, just print error and let quit_on_error handle exit
            sys.stderr.write(f"Error: Unknown command: '{command}'\n")

    def onecmd_plus_hooks(self, line: str, *, add_to_history: bool = True, **kwargs) -> bool:
        """Override to capture command output for $TSIM_RESULT."""
        import io
        from contextlib import redirect_stdout
        
        # Check if this is a tsimsh command (not a variable assignment or shell command)
        if not self.variable_manager.process_command_for_assignment(line):
            # Parse the command to check if it's a known tsimsh command
            statement = self.statement_parser.parse(line)
            tsimsh_commands = ['network', 'trace', 'service', 'host', 'facts', 'print', 'variables', 'unset']
            
            if statement.command in tsimsh_commands:
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
                    # Store in $TSIM_RESULT
                    if output:
                        self.variable_manager.set_variable('TSIM_RESULT', output.strip())
                    # Write output to original stdout
                    original_stdout.write(output)
                    return result
                finally:
                    # Restore stdout
                    self.stdout = original_stdout
            else:
                # For non-tsimsh commands, execute normally
                try:
                    # Try with add_to_history parameter (newer cmd2 versions)
                    return super().onecmd_plus_hooks(line, add_to_history=add_to_history, **kwargs)
                except TypeError:
                    # Fall back to without parameter (older cmd2 versions)
                    return super().onecmd_plus_hooks(line)
        
        # Variable assignment was already handled
        return False
    
    def precmd(self, statement: cmd2.Statement) -> cmd2.Statement:
        """
        This hook is called before the command is executed.
        It handles variable substitutions.
        """
        # statement.raw is the raw input line
        line = statement.raw
        substituted_line = self.variable_manager.substitute_variables(line)
        
        # Create a new statement with the substituted line
        new_statement = self.statement_parser.parse(substituted_line)
        
        return super().precmd(new_statement)
    
    
    def do_EOF(self, line):
        """Handle Ctrl+D - exit shell."""
        if self.is_interactive:
            self.poutput(f"\n{Fore.CYAN}Goodbye!{Style.RESET_ALL}")
        return True
    
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
            
            self.facts_handler = FactsCommands(self)
            self.network_handler = NetworkCommands(self)
            self.host_handler = HostCommands(self)
            self.service_handler = ServiceCommands(self)
            self.completion_handler = CompletionCommands(self)
            self.trace_handler = TraceCommands(self)
            
        except ImportError as e:
            self.poutput(f"{Fore.RED}Error loading command handlers: {e}{Style.RESET_ALL}")
            # Continue with basic shell functionality
    
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
            return self.facts_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Facts commands not available{Style.RESET_ALL}")
    
    def complete_facts(self, text, line, begidx, endidx):
        """Provide completion for facts command."""
        if hasattr(self, 'facts_handler'):
            return self.facts_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_network(self, args):
        """Manage network namespace simulation."""
        if hasattr(self, 'network_handler'):
            return self.network_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Network commands not available{Style.RESET_ALL}")
    
    def complete_network(self, text, line, begidx, endidx):
        """Provide completion for network command."""
        if hasattr(self, 'network_handler'):
            return self.network_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_host(self, args):
        """Manage dynamic host creation and removal."""
        if hasattr(self, 'host_handler'):
            return self.host_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Host commands not available{Style.RESET_ALL}")
    
    def complete_host(self, text, line, begidx, endidx):
        """Provide completion for host command."""
        if hasattr(self, 'host_handler'):
            return self.host_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_service(self, args):
        """Manage TCP/UDP services in network simulation."""
        if hasattr(self, 'service_handler'):
            return self.service_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Service commands not available{Style.RESET_ALL}")
    
    def complete_service(self, text, line, begidx, endidx):
        """Provide completion for service command."""
        if hasattr(self, 'service_handler'):
            return self.service_handler.complete_command(text, line, begidx, endidx)
        return []
    
    
    def do_completion(self, args):
        """Generate shell completion scripts."""
        if hasattr(self, 'completion_handler'):
            return self.completion_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Completion commands not available{Style.RESET_ALL}")
    
    def complete_completion(self, text, line, begidx, endidx):
        """Provide completion for completion command."""
        if hasattr(self, 'completion_handler'):
            return self.completion_handler.complete_command(text, line, begidx, endidx)
        return []
    
    def do_trace(self, args):
        """Perform reverse path tracing between source and destination."""
        if hasattr(self, 'trace_handler'):
            return self.trace_handler.handle_command(args)
        else:
            self.poutput(f"{Fore.RED}Trace command not available{Style.RESET_ALL}")
    
    def complete_trace(self, text, line, begidx, endidx):
        """Provide completion for trace command."""
        if hasattr(self, 'trace_handler'):
            return self.trace_handler.complete_command(text, line, begidx, endidx)
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
        super().do_help(args)
    
    def do_history(self, args):
        """Show command history."""
        # Always show full history regardless of context
        super().do_history(args)
    
    def help_facts(self):
        """Help for facts command."""
        self.poutput(f"{Fore.CYAN}Facts Management Commands:{Style.RESET_ALL}")
        self.poutput("  facts collect [--inventory FILE] [--output-dir DIR]")
        self.poutput("    Collect routing facts from network devices")
        self.poutput("  facts process [--input-dir DIR] [--output-dir DIR] [--validate]")
        self.poutput("    Process raw facts into structured JSON")
        self.poutput("  facts validate [--facts-dir DIR] [--verbose]")
        self.poutput("    Validate processed facts files")
    
    def help_network(self):
        """Help for network command."""
        self.poutput(f"{Fore.CYAN}Network Management Commands:{Style.RESET_ALL}")
        self.poutput("  network setup [--limit PATTERN] [--verify] [--verbose]")
        self.poutput("    Setup network namespace simulation")
        self.poutput("  network status [function] [--limit PATTERN] [--json] [--verbose]")
        self.poutput("    Show network namespace status")
        self.poutput("  network clean [--force] [--limit PATTERN] [--verbose]")
        self.poutput("    Clean up network namespaces")
        self.poutput("  network test [--source IP] [--destination IP] [--all] [--test-type TYPE] [--verbose]")
        self.poutput("    Test network connectivity")
    
    def help_host(self):
        """Help for host command."""
        self.poutput(f"{Fore.CYAN}Host Management Commands:{Style.RESET_ALL}")
        self.poutput("  host add --name NAME --primary-ip IP/MASK --connect-to ROUTER")
        self.poutput("    Add a new host to the network")
        self.poutput("  host list [--format FORMAT] [--verbose]")
        self.poutput("    List all hosts")
        self.poutput("  host remove --name NAME [--force]")
        self.poutput("    Remove a host from the network")
        self.poutput("  host clean [--force]")
        self.poutput("    Remove all hosts")
    
    def help_service(self):
        """Help for service command."""
        self.poutput(f"{Fore.CYAN}Service Management Commands:{Style.RESET_ALL}")
        self.poutput("  service start --ip IP --port PORT [--protocol PROTO] [--name NAME]")
        self.poutput("    Start a TCP/UDP service")
        self.poutput("  service test --source IP --dest IP:PORT [--protocol PROTO]")
        self.poutput("    Test service connectivity")
        self.poutput("  service list [--format FORMAT] [--verbose]")
        self.poutput("    List all active services")
        self.poutput("  service stop --ip IP --port PORT [--protocol PROTO]")
        self.poutput("    Stop a service")
        self.poutput("  service clean [--force]")
        self.poutput("    Stop all services")
    
    
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
        """Help for trace command."""
        self.poutput(f"{Fore.CYAN}Trace Command:{Style.RESET_ALL}")
        self.poutput("  trace -s SOURCE_IP -d DESTINATION_IP [--json] [--verbose]")
        self.poutput("    Perform reverse path tracing between source and destination")
        self.poutput("")
        self.poutput("Options:")
        self.poutput("  -s, --source       Source IP address (required)")
        self.poutput("  -d, --destination  Destination IP address (required)")
        self.poutput("  -j, --json         Output in JSON format")
        self.poutput("  -v, --verbose      Verbose output (can be used multiple times)")
        self.poutput("  --controller-ip    Ansible controller IP (auto-detected if not provided)")
        self.poutput("")
        self.poutput("Examples:")
        self.poutput("  trace -s 10.1.1.1 -d 10.3.1.1")
        self.poutput("  trace -s 10.1.2.3 -d 192.168.1.1 --json")
        self.poutput("  trace -s 10.2.1.1 -d 10.1.3.1 -vv")



def main():
    """Main entry point for running the shell standalone."""
    shell = TracerouteSimulatorShell()
    shell.cmdloop()


if __name__ == '__main__':
    main()

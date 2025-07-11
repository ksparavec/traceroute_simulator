"""
Completion command handler for generating shell completion scripts.
"""

import os
import argparse
from typing import Optional, List

try:
    from cmd2 import Cmd2ArgumentParser, choices_provider
except ImportError:
    # Fallback for older cmd2 versions
    from argparse import ArgumentParser as Cmd2ArgumentParser
    def choices_provider(func):
        return func

from .base import BaseCommandHandler


class CompletionCommands(BaseCommandHandler):
    """Handler for shell completion commands."""
    
    @choices_provider
    def shell_choices(self) -> List[str]:
        """Provide shell type choices for completion."""
        return ['bash', 'zsh', 'fish']
    
    def create_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for completion commands."""
        parser = Cmd2ArgumentParser(prog='completion', description='Generate shell completion scripts')
        subparsers = parser.add_subparsers(dest='subcommand', help='Completion subcommands')
        
        # Generate subcommand
        generate_parser = subparsers.add_parser('generate', help='Generate completion script')
        generate_parser.add_argument('--shell', '-s', required=True,
                                   choices=['bash', 'zsh', 'fish'],
                                   help='Shell type')
        generate_parser.add_argument('--output-file', '-o',
                                   help='Output file path')
        generate_parser.add_argument('--verbose', '-v', action='store_true',
                                   help='Verbose output')
        
        # Install subcommand
        install_parser = subparsers.add_parser('install', help='Install completion script')
        install_parser.add_argument('--shell', '-s', required=True,
                                  choices=['bash', 'zsh', 'fish'],
                                  help='Shell type')
        install_parser.add_argument('--global', dest='global_install', action='store_true',
                                  help='Install globally for all users')
        
        # Uninstall subcommand
        uninstall_parser = subparsers.add_parser('uninstall', help='Uninstall completion script')
        uninstall_parser.add_argument('--shell', '-s', required=True,
                                    choices=['bash', 'zsh', 'fish'],
                                    help='Shell type')
        uninstall_parser.add_argument('--global', dest='global_install', action='store_true',
                                    help='Uninstall from global location')
        
        return parser
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle parsed completion command."""
        if not args.subcommand:
            self.shell.help_completion()
            return None
        
        # Handle help specially
        if args.subcommand == 'help':
            self.shell.help_completion()
            return None
        
        if args.subcommand == 'generate':
            return self._generate_completion(args)
        elif args.subcommand == 'install':
            return self._install_completion(args)
        elif args.subcommand == 'uninstall':
            return self._uninstall_completion(args)
        else:
            self.error(f"Unknown completion subcommand: {args.subcommand}")
            self.shell.help_completion()
            return 1
    
    def handle_command(self, args: str) -> Optional[int]:
        """Handle completion command with subcommands (legacy support)."""
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            return 1
    
    
    def _generate_completion(self, args: argparse.Namespace) -> int:
        """Generate completion script for specified shell."""
        self.info(f"Generating {args.shell} completion script...")
        
        # Generate completion script content
        completion_script = self._create_completion_script(parsed_args.shell)
        
        # Determine output file
        if parsed_args.output_file:
            output_file = parsed_args.output_file
        else:
            output_file = f"tsim-completion.{parsed_args.shell}"
        
        # Write completion script
        try:
            with open(output_file, 'w') as f:
                f.write(completion_script)
            
            self.success(f"Completion script generated: {output_file}")
            
            # Show installation instructions
            self._show_installation_instructions(parsed_args.shell, output_file)
            
            return 0
            
        except Exception as e:
            self.error(f"Failed to write completion script: {e}")
            return 1
    
    def _install_completion(self, args: list) -> int:
        """Install completion script."""
        parser = argparse.ArgumentParser(prog='completion install',
                                       description='Install completion script')
        parser.add_argument('--shell', '-s', required=True,
                          choices=['bash', 'zsh', 'fish'],
                          help='Shell type')
        parser.add_argument('--global', '-g', action='store_true',
                          help='Install globally (system-wide)')
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Verbose output')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        self.info(f"Installing {parsed_args.shell} completion...")
        
        # Generate completion script first
        completion_script = self._create_completion_script(parsed_args.shell)
        
        # Determine installation path
        if parsed_args.shell == 'bash':
            if getattr(parsed_args, 'global', False):
                install_dir = "/etc/bash_completion.d"
            else:
                install_dir = os.path.expanduser("~/.local/share/bash-completion/completions")
            filename = "tsim"
        elif parsed_args.shell == 'zsh':
            if getattr(parsed_args, 'global', False):
                install_dir = "/usr/local/share/zsh/site-functions"
            else:
                install_dir = os.path.expanduser("~/.local/share/zsh/site-functions")
            filename = "_tsim"
        elif parsed_args.shell == 'fish':
            if getattr(parsed_args, 'global', False):
                install_dir = "/usr/share/fish/completions"
            else:
                install_dir = os.path.expanduser("~/.config/fish/completions")
            filename = "tsim.fish"
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(install_dir, exist_ok=True)
        except OSError as e:
            self.error(f"Failed to create directory {install_dir}: {e}")
            return 1
        
        # Install completion script
        install_path = os.path.join(install_dir, filename)
        
        try:
            with open(install_path, 'w') as f:
                f.write(completion_script)
            
            self.success(f"Completion installed to: {install_path}")
            self.info(f"Restart your {parsed_args.shell} shell or run: source {install_path}")
            
            return 0
            
        except Exception as e:
            self.error(f"Failed to install completion: {e}")
            return 1
    
    def _uninstall_completion(self, args: list) -> int:
        """Uninstall completion script."""
        parser = argparse.ArgumentParser(prog='completion uninstall',
                                       description='Uninstall completion script')
        parser.add_argument('--shell', '-s', required=True,
                          choices=['bash', 'zsh', 'fish'],
                          help='Shell type')
        parser.add_argument('--global', '-g', action='store_true',
                          help='Uninstall from global location')
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Verbose output')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        self.info(f"Uninstalling {parsed_args.shell} completion...")
        
        # Determine installation path
        if parsed_args.shell == 'bash':
            if getattr(parsed_args, 'global', False):
                install_dir = "/etc/bash_completion.d"
            else:
                install_dir = os.path.expanduser("~/.local/share/bash-completion/completions")
            filename = "tsim"
        elif parsed_args.shell == 'zsh':
            if getattr(parsed_args, 'global', False):
                install_dir = "/usr/local/share/zsh/site-functions"
            else:
                install_dir = os.path.expanduser("~/.local/share/zsh/site-functions")
            filename = "_tsim"
        elif parsed_args.shell == 'fish':
            if getattr(parsed_args, 'global', False):
                install_dir = "/usr/share/fish/completions"
            else:
                install_dir = os.path.expanduser("~/.config/fish/completions")
            filename = "tsim.fish"
        
        install_path = os.path.join(install_dir, filename)
        
        # Remove completion script
        try:
            if os.path.exists(install_path):
                os.remove(install_path)
                self.success(f"Completion uninstalled from: {install_path}")
            else:
                self.warning(f"Completion not found at: {install_path}")
            
            return 0
            
        except Exception as e:
            self.error(f"Failed to uninstall completion: {e}")
            return 1
    
    def _create_completion_script(self, shell: str) -> str:
        """Create completion script content for the specified shell."""
        if shell == 'bash':
            return self._create_bash_completion()
        elif shell == 'zsh':
            return self._create_zsh_completion()
        elif shell == 'fish':
            return self._create_fish_completion()
        else:
            return ""
    
    def _create_bash_completion(self) -> str:
        """Create bash completion script."""
        return """#!/bin/bash
# Bash completion for tsim (Traceroute Simulator Shell)

_tsim_completion() {
    local cur prev words cword
    _init_completion || return
    
    # Main commands
    local commands="facts network host service mtr completion status help exit quit"
    
    # Subcommands
    local facts_commands="collect process validate"
    local network_commands="setup status clean test"
    local host_commands="add list remove clean"
    local service_commands="start test list stop clean"
    local mtr_commands="route analyze real reverse"
    local completion_commands="generate install uninstall"
    
    case $cword in
        1)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            ;;
        2)
            case "${words[1]}" in
                facts)
                    COMPREPLY=($(compgen -W "$facts_commands" -- "$cur"))
                    ;;
                network)
                    COMPREPLY=($(compgen -W "$network_commands" -- "$cur"))
                    ;;
                host)
                    COMPREPLY=($(compgen -W "$host_commands" -- "$cur"))
                    ;;
                service)
                    COMPREPLY=($(compgen -W "$service_commands" -- "$cur"))
                    ;;
                mtr)
                    COMPREPLY=($(compgen -W "$mtr_commands" -- "$cur"))
                    ;;
                completion)
                    COMPREPLY=($(compgen -W "$completion_commands" -- "$cur"))
                    ;;
            esac
            ;;
        *)
            # Option completion
            case "$prev" in
                --shell|-s)
                    COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur"))
                    ;;
                --protocol|-p)
                    COMPREPLY=($(compgen -W "tcp udp icmp" -- "$cur"))
                    ;;
                --format|-f)
                    COMPREPLY=($(compgen -W "text json" -- "$cur"))
                    ;;
                --inventory|-i|--output-file|-o|--input-dir|--output-dir)
                    COMPREPLY=($(compgen -f -- "$cur"))
                    ;;
            esac
            ;;
    esac
}

complete -F _tsim_completion tsim
"""
    
    def _create_zsh_completion(self) -> str:
        """Create zsh completion script."""
        return """#compdef tsim
# Zsh completion for tsim (Traceroute Simulator Shell)

_tsim() {
    local context state line
    
    _arguments -C \\
        "1: :->command" \\
        "*: :->args" && return 0
    
    case $state in
        command)
            local commands=(
                "facts:Manage routing facts collection and processing"
                "network:Manage network namespace simulation"
                "host:Manage dynamic host creation and removal"
                "service:Manage TCP/UDP services"
                "mtr:Perform traceroute simulation and analysis"
                "completion:Generate shell completion scripts"
                "status:Show shell status"
                "help:Show help information"
                "exit:Exit the shell"
                "quit:Quit the shell"
            )
            _describe 'command' commands
            ;;
        args)
            case $words[2] in
                facts)
                    local facts_commands=(
                        "collect:Collect routing facts"
                        "process:Process raw facts"
                        "validate:Validate facts files"
                    )
                    _describe 'facts command' facts_commands
                    ;;
                network)
                    local network_commands=(
                        "setup:Setup network simulation"
                        "status:Show network status"
                        "clean:Clean network namespaces"
                        "test:Test network connectivity"
                    )
                    _describe 'network command' network_commands
                    ;;
                host)
                    local host_commands=(
                        "add:Add a host"
                        "list:List hosts"
                        "remove:Remove a host"
                        "clean:Remove all hosts"
                    )
                    _describe 'host command' host_commands
                    ;;
                service)
                    local service_commands=(
                        "start:Start a service"
                        "test:Test service connectivity"
                        "list:List services"
                        "stop:Stop a service"
                        "clean:Stop all services"
                    )
                    _describe 'service command' service_commands
                    ;;
                mtr)
                    local mtr_commands=(
                        "route:Traceroute simulation"
                        "analyze:Analyze forwarding rules"
                        "real:Execute real MTR"
                        "reverse:Reverse path tracing"
                    )
                    _describe 'mtr command' mtr_commands
                    ;;
                completion)
                    local completion_commands=(
                        "generate:Generate completion script"
                        "install:Install completion script"
                        "uninstall:Uninstall completion script"
                    )
                    _describe 'completion command' completion_commands
                    ;;
            esac
            ;;
    esac
}

_tsim "$@"
"""
    
    def _create_fish_completion(self) -> str:
        """Create fish completion script."""
        return """# Fish completion for tsim (Traceroute Simulator Shell)

# Main commands
complete -c tsim -f -n "__fish_use_subcommand" -a "facts" -d "Manage routing facts"
complete -c tsim -f -n "__fish_use_subcommand" -a "network" -d "Manage network simulation"
complete -c tsim -f -n "__fish_use_subcommand" -a "host" -d "Manage hosts"
complete -c tsim -f -n "__fish_use_subcommand" -a "service" -d "Manage services"
complete -c tsim -f -n "__fish_use_subcommand" -a "mtr" -d "Traceroute and analysis"
complete -c tsim -f -n "__fish_use_subcommand" -a "completion" -d "Completion scripts"
complete -c tsim -f -n "__fish_use_subcommand" -a "status" -d "Show shell status"
complete -c tsim -f -n "__fish_use_subcommand" -a "help" -d "Show help"
complete -c tsim -f -n "__fish_use_subcommand" -a "exit" -d "Exit shell"
complete -c tsim -f -n "__fish_use_subcommand" -a "quit" -d "Quit shell"

# Facts subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from facts" -a "collect" -d "Collect routing facts"
complete -c tsim -f -n "__fish_seen_subcommand_from facts" -a "process" -d "Process raw facts"
complete -c tsim -f -n "__fish_seen_subcommand_from facts" -a "validate" -d "Validate facts files"

# Network subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from network" -a "setup" -d "Setup network simulation"
complete -c tsim -f -n "__fish_seen_subcommand_from network" -a "status" -d "Show network status"
complete -c tsim -f -n "__fish_seen_subcommand_from network" -a "clean" -d "Clean network namespaces"
complete -c tsim -f -n "__fish_seen_subcommand_from network" -a "test" -d "Test network connectivity"

# Host subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from host" -a "add" -d "Add a host"
complete -c tsim -f -n "__fish_seen_subcommand_from host" -a "list" -d "List hosts"
complete -c tsim -f -n "__fish_seen_subcommand_from host" -a "remove" -d "Remove a host"
complete -c tsim -f -n "__fish_seen_subcommand_from host" -a "clean" -d "Remove all hosts"

# Service subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from service" -a "start" -d "Start a service"
complete -c tsim -f -n "__fish_seen_subcommand_from service" -a "test" -d "Test service connectivity"
complete -c tsim -f -n "__fish_seen_subcommand_from service" -a "list" -d "List services"
complete -c tsim -f -n "__fish_seen_subcommand_from service" -a "stop" -d "Stop a service"
complete -c tsim -f -n "__fish_seen_subcommand_from service" -a "clean" -d "Stop all services"

# MTR subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from mtr" -a "route" -d "Traceroute simulation"
complete -c tsim -f -n "__fish_seen_subcommand_from mtr" -a "analyze" -d "Analyze forwarding rules"
complete -c tsim -f -n "__fish_seen_subcommand_from mtr" -a "real" -d "Execute real MTR"
complete -c tsim -f -n "__fish_seen_subcommand_from mtr" -a "reverse" -d "Reverse path tracing"

# Completion subcommands
complete -c tsim -f -n "__fish_seen_subcommand_from completion" -a "generate" -d "Generate completion script"
complete -c tsim -f -n "__fish_seen_subcommand_from completion" -a "install" -d "Install completion script"
complete -c tsim -f -n "__fish_seen_subcommand_from completion" -a "uninstall" -d "Uninstall completion script"

# Common options
complete -c tsim -l help -d "Show help"
complete -c tsim -l verbose -s v -d "Verbose output"
complete -c tsim -l format -s f -a "text json" -d "Output format"
complete -c tsim -l protocol -s p -a "tcp udp icmp" -d "Protocol"
complete -c tsim -l shell -s s -a "bash zsh fish" -d "Shell type"
"""
    
    def _show_installation_instructions(self, shell: str, script_path: str):
        """Show installation instructions for the completion script."""
        self.info(f"To install {shell} completion:")
        
        if shell == 'bash':
            self.shell.poutput(f"  mkdir -p ~/.local/share/bash-completion/completions")
            self.shell.poutput(f"  cp {script_path} ~/.local/share/bash-completion/completions/tsim")
            self.shell.poutput(f"  source ~/.bashrc")
        elif shell == 'zsh':
            self.shell.poutput(f"  mkdir -p ~/.local/share/zsh/site-functions")
            self.shell.poutput(f"  cp {script_path} ~/.local/share/zsh/site-functions/_tsim")
            self.shell.poutput(f"  exec zsh")
        elif shell == 'fish':
            self.shell.poutput(f"  mkdir -p ~/.config/fish/completions")
            self.shell.poutput(f"  cp {script_path} ~/.config/fish/completions/tsim.fish")
            self.shell.poutput(f"  Restart fish shell")
        
        self.info("Or use: completion install --shell " + shell)
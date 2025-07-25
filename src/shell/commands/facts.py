#!/usr/bin/env -S python3 -B -u
"""
Facts command handler for collecting and processing routing facts.
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


class FactsCommands(BaseCommandHandler):
    """Handler for facts-related commands."""
    
    def get_subcommand_names(self) -> List[str]:
        """Get list of facts subcommands."""
        return ['collect', 'process', 'validate']
    
    @choices_provider
    def directory_choices(self) -> List[str]:
        """Provide directory path choices for completion."""
        import glob
        dirs = []
        if os.path.exists('.'):
            dirs.extend([d for d in glob.glob('*') if os.path.isdir(d)])
        if self.facts_dir and os.path.exists(self.facts_dir):
            dirs.append(self.facts_dir)
        return dirs
    
    @choices_provider
    def inventory_choices(self) -> List[str]:
        """Provide inventory file choices for completion."""
        import glob
        files = glob.glob('*.ini') + glob.glob('*.yml') + glob.glob('*.yaml')
        if os.path.exists('inventory.ini'):
            files.append('inventory.ini')
        if os.path.exists('hosts.ini'):
            files.append('hosts.ini')
        return list(set(files))
    
    def create_parser(self) -> Cmd2ArgumentParser:
        """Create the argument parser for facts commands."""
        parser = Cmd2ArgumentParser(prog='facts', description='Manage routing facts collection and processing')
        subparsers = parser.add_subparsers(dest='subcommand', help='Facts subcommands')
        
        # Collect subcommand
        collect_parser = subparsers.add_parser('collect', help='Collect routing facts from network devices')
        collect_parser.add_argument('--inventory', '-i',
                                  choices_provider=self.inventory_choices,
                                  help='Ansible inventory file')
        collect_parser.add_argument('--output-dir', '-o',
                                  choices_provider=self.directory_choices,
                                  help='Output directory for facts')
        collect_parser.add_argument('--test-mode', action='store_true',
                                  help='Use test mode (process existing raw facts)')
        collect_parser.add_argument('--verbose', '-v', action='store_true',
                                  help='Verbose output')
        
        # Process subcommand
        process_parser = subparsers.add_parser('process', help='Process raw facts into structured JSON')
        process_parser.add_argument('--input-dir', '-i',
                                  choices_provider=self.directory_choices,
                                  help='Input directory with raw facts')
        process_parser.add_argument('--output-dir', '-o',
                                  choices_provider=self.directory_choices,
                                  help='Output directory for processed facts')
        process_parser.add_argument('--validate', action='store_true',
                                  help='Validate processed facts')
        process_parser.add_argument('--verbose', '-v', action='store_true',
                                  help='Verbose output')
        
        # Validate subcommand
        validate_parser = subparsers.add_parser('validate', help='Validate processed facts files')
        validate_parser.add_argument('--facts-dir', '-d',
                                   choices_provider=self.directory_choices,
                                   help='Facts directory to validate')
        validate_parser.add_argument('--verbose', '-v', action='store_true',
                                   help='Verbose output')
        
        return parser
    
    def handle_parsed_command(self, args: argparse.Namespace) -> Optional[int]:
        """Handle parsed facts command."""
        if not args.subcommand:
            self.shell.help_facts()
            return None
        
        # Handle help specially
        if args.subcommand == 'help':
            self.shell.help_facts()
            return None
        
        if args.subcommand == 'collect':
            return self._collect_facts(args)
        elif args.subcommand == 'process':
            return self._process_facts(args)
        elif args.subcommand == 'validate':
            return self._validate_facts(args)
        else:
            self.error(f"Unknown facts subcommand: {args.subcommand}")
            self.shell.help_facts()
            return 1
    
    def _handle_command_impl(self, args: str) -> Optional[int]:
        """Handle facts command with subcommands (legacy support)."""
        # Check for help flags first
        args_list = args.strip().split() if args.strip() else []
        if '--help' in args_list or '-h' in args_list:
            self.shell.help_facts()
            return 0
            
        # This method is kept for backward compatibility
        parser = self.create_parser()
        try:
            parsed_args = parser.parse_args(self._split_args(args))
            return self.handle_parsed_command(parsed_args)
        except SystemExit:
            return 1
    
    
    def _collect_facts(self, args: argparse.Namespace) -> int:
        """Collect routing facts from network devices."""
        # Determine what to run
        if args.test_mode:
            return self._collect_test_facts(args)
        else:
            return self._collect_real_facts(args)
    
    def _collect_test_facts(self, args) -> int:
        """Collect facts in test mode."""
        self.info("Collecting facts in test mode...")
        
        # Run the ansible playbook in test mode
        if 'site-packages' in self.project_root:
            # We're in a package, need to extract playbook to temp location
            import tempfile
            import shutil
            try:
                import importlib.resources as pkg_resources
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Extract ansible directory to temp location
                    ansible_dir = os.path.join(tmpdir, 'ansible')
                    os.makedirs(ansible_dir)
                    
                    # Copy all ansible files
                    for file in pkg_resources.files('tsim.ansible').iterdir():
                        if file.is_file():
                            dest_path = os.path.join(ansible_dir, file.name)
                            with file.open('rb') as src_f:
                                with open(dest_path, 'wb') as dest_f:
                                    dest_f.write(src_f.read())
                    
                    playbook_path = os.path.join(ansible_dir, 'get_tsim_facts.yml')
                    if not os.path.exists(playbook_path):
                        self.error("Playbook not found in package")
                        return 1
                    
                    # Continue with the rest of the function using tmpdir as cwd
                    return self._run_ansible_playbook(playbook_path, args, tmpdir)
            except Exception as e:
                self.error(f"Error extracting playbook from package: {e}")
                return 1
        else:
            playbook_path = os.path.join(self.project_root, 'ansible', 'get_tsim_facts.yml')
            if not self.check_script_exists(playbook_path):
                return 1
            return self._run_ansible_playbook(playbook_path, args, self.project_root)
    
    def _run_ansible_playbook(self, playbook_path: str, args, cwd: str) -> int:
        """Run ansible playbook with given arguments."""
        # Build ansible command
        cmd = ['ansible-playbook', playbook_path]
        
        # Add test=true for test mode, or normal arguments for real mode
        if hasattr(args, 'test_mode') and args.test_mode:
            cmd.extend(['-e', 'test=true'])
        else:
            # Real mode - add output_dir if specified
            if hasattr(args, 'output_dir') and args.output_dir:
                cmd.extend(['-e', f'output_dir={args.output_dir}'])
        
        if args.inventory:
            # For packaged mode, we need to handle inventory path carefully
            if 'site-packages' in self.project_root and not os.path.isabs(args.inventory):
                # If it's a relative path and we're in package mode, use current directory
                inventory_path = os.path.join(os.getcwd(), args.inventory)
                cmd.extend(['-i', inventory_path])
            else:
                cmd.extend(['-i', args.inventory])
        else:
            # Use default test inventory if in test mode
            if hasattr(args, 'test_mode') and args.test_mode:
                if 'site-packages' in self.project_root:
                    # Skip inventory for now in package mode
                    pass
                else:
                    inventory_path = os.path.join(self.project_root, 'tests', 'inventory.yml')
                    if os.path.exists(inventory_path):
                        cmd.extend(['-i', inventory_path])
        
        if args.verbose:
            cmd.append('-v')
        
        # Run the command
        try:
            import subprocess
            result = subprocess.run(cmd, cwd=cwd, 
                                  capture_output=True, text=True)
            
            if result.stdout:
                self.shell.poutput(result.stdout)
            if result.stderr:
                self.shell.poutput(result.stderr)
            
            if result.returncode == 0:
                if hasattr(args, 'test_mode') and args.test_mode:
                    self.success("Test facts collection completed successfully")
                    self.info("Facts generated in /tmp/traceroute_test_output/")
                    # Update facts directory for this session
                    self.facts_dir = "/tmp/traceroute_test_output"
                    os.environ['TRACEROUTE_SIMULATOR_FACTS'] = self.facts_dir
                else:
                    self.success("Facts collection completed successfully")
                    if hasattr(args, 'output_dir') and args.output_dir:
                        self.info(f"Facts saved to: {args.output_dir}")
            else:
                self.error("Facts collection failed")
            
            return result.returncode
            
        except FileNotFoundError:
            self.error("ansible-playbook not found. Please install Ansible.")
            return 1
        except Exception as e:
            self.error(f"Error running facts collection: {e}")
            return 1
    
    def _collect_real_facts(self, args) -> int:
        """Collect facts from real network devices."""
        self.info("Collecting facts from network devices...")
        
        # Handle package vs development mode
        if 'site-packages' in self.project_root:
            # We're in a package, need to extract playbook to temp location
            import tempfile
            import shutil
            try:
                import importlib.resources as pkg_resources
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Extract ansible directory to temp location
                    ansible_dir = os.path.join(tmpdir, 'ansible')
                    os.makedirs(ansible_dir)
                    
                    # Copy all ansible files
                    for file in pkg_resources.files('tsim.ansible').iterdir():
                        if file.is_file():
                            dest_path = os.path.join(ansible_dir, file.name)
                            with file.open('rb') as src_f:
                                with open(dest_path, 'wb') as dest_f:
                                    dest_f.write(src_f.read())
                    
                    playbook_path = os.path.join(ansible_dir, 'get_tsim_facts.yml')
                    if not os.path.exists(playbook_path):
                        self.error("Playbook not found in package")
                        return 1
                    
                    # Continue with the rest of the function using tmpdir as cwd
                    return self._run_ansible_playbook(playbook_path, args, tmpdir)
            except Exception as e:
                self.error(f"Error extracting playbook from package: {e}")
                return 1
        else:
            playbook_path = os.path.join(self.project_root, 'ansible', 'get_tsim_facts.yml')
            if not self.check_script_exists(playbook_path):
                return 1
            return self._run_ansible_playbook(playbook_path, args, self.project_root)
    
    def _process_facts(self, args: argparse.Namespace) -> int:
        """Process raw facts into structured JSON."""
        
        self.info("Processing raw facts...")
        
        # Use the process_all_facts.py script
        script_path = self.get_script_path('ansible/process_all_facts.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = []
        
        if hasattr(args, 'input_dir') and args.input_dir:
            cmd_args.extend(['--input-dir', args.input_dir])
        
        if hasattr(args, 'output_dir') and args.output_dir:
            cmd_args.extend(['--output-dir', args.output_dir])
        
        if hasattr(args, 'verbose') and args.verbose:
            cmd_args.append('--verbose')
        
        cmd_args.append('--create-dirs')
        
        # Run the script
        returncode = self.run_script_with_output(script_path, cmd_args)
        
        if returncode == 0:
            self.success("Facts processing completed successfully")
            if hasattr(args, 'validate') and args.validate:
                # Create a simple namespace for validate
                validate_args = argparse.Namespace(
                    facts_dir=None,
                    verbose=args.verbose if hasattr(args, 'verbose') else False
                )
                return self._validate_facts(validate_args)
        else:
            self.error("Facts processing failed")
        
        return returncode
    
    def _validate_facts(self, args: argparse.Namespace) -> int:
        """Validate processed facts files."""
        facts_dir = args.facts_dir if hasattr(args, 'facts_dir') and args.facts_dir else self.facts_dir
        
        if not facts_dir:
            self.error("No facts directory specified. Set TRACEROUTE_SIMULATOR_FACTS or use --facts-dir")
            return 1
            
        if not os.path.exists(facts_dir):
            self.error(f"Facts directory not found: {facts_dir}")
            return 1
        
        self.info(f"Validating facts in {facts_dir}...")
        
        # Check for JSON files
        json_files = [f for f in os.listdir(facts_dir) if f.endswith('.json')]
        
        if not json_files:
            self.error(f"No JSON files found in {facts_dir}")
            return 1
        
        # Validate each JSON file
        import json
        valid_files = 0
        
        for json_file in json_files:
            file_path = os.path.join(facts_dir, json_file)
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                # Basic validation
                if isinstance(data, dict):
                    if hasattr(args, 'verbose') and args.verbose:
                        self.info(f"✓ {json_file} - Valid JSON with {len(data)} keys")
                    valid_files += 1
                else:
                    self.warning(f"✗ {json_file} - Invalid structure (not a dict)")
                    
            except json.JSONDecodeError as e:
                self.error(f"✗ {json_file} - Invalid JSON: {e}")
            except Exception as e:
                self.error(f"✗ {json_file} - Error reading file: {e}")
        
        if valid_files == len(json_files):
            self.success(f"All {valid_files} facts files are valid")
            return 0
        else:
            self.error(f"Only {valid_files}/{len(json_files)} facts files are valid")
            return 1
    
    def complete_command(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """Provide completion for facts command arguments."""
        # Parse the line to understand what we're completing
        args = line.split()
        
        # If we're typing the second word (the subcommand)
        if len(args) == 1 or (len(args) == 2 and not line.endswith(' ')):
            subcommands = self.get_subcommand_names()
            if len(args) == 1:
                # Just "facts" typed, return all subcommands
                return subcommands
            else:
                # "facts <partial>", return matching subcommands
                return [cmd for cmd in subcommands if cmd.startswith(args[1])]
        
        # We have a subcommand, now handle argument completion
        subcommand = args[1]
        
        # For specific subcommands, provide appropriate completions
        if subcommand == 'collect':
            # Provide argument names that haven't been used yet
            used_args = set(args)
            available_args = ['--inventory', '--output-dir', '--test', '--verbose']
            
            # Check if we're completing a value for a specific argument
            if len(args) >= 2 and args[-2] == '--inventory':
                return self.inventory_choices()
            elif len(args) >= 2 and args[-2] == '--output-dir':
                return self.directory_choices()
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'process':
            used_args = set(args)
            available_args = ['--input-dir', '--output-dir', '--create-dirs', '--validate', '--verbose']
            
            # Check if we're completing a value for a specific argument
            if len(args) >= 2 and args[-2] in ['--input-dir', '--output-dir']:
                return self.directory_choices()
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        elif subcommand == 'validate':
            used_args = set(args)
            available_args = ['--facts-dir', '--verbose']
            
            # Check if we're completing a value for --facts-dir
            if len(args) >= 2 and args[-2] == '--facts-dir':
                return self.directory_choices()
            
            return [arg for arg in available_args if arg not in used_args and arg.startswith(text)]
        
        return []
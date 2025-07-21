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
        playbook_path = os.path.join(self.project_root, 'ansible', 'get_tsim_facts.yml')
        if not self.check_script_exists(playbook_path):
            return 1
        
        # Build ansible command
        cmd = ['ansible-playbook', playbook_path, '-e', 'test=true']
        
        if args.inventory:
            cmd.extend(['-i', args.inventory])
        else:
            # Use default test inventory
            inventory_path = os.path.join(self.project_root, 'tests', 'inventory.yml')
            if os.path.exists(inventory_path):
                cmd.extend(['-i', inventory_path])
        
        if args.verbose:
            cmd.append('-v')
        
        # Run the command
        try:
            import subprocess
            result = subprocess.run(cmd, cwd=self.project_root, 
                                  capture_output=True, text=True)
            
            if result.stdout:
                self.shell.poutput(result.stdout)
            if result.stderr:
                self.shell.poutput(result.stderr)
            
            if result.returncode == 0:
                self.success("Test facts collection completed successfully")
                self.info("Facts generated in /tmp/traceroute_test_output/")
                # Update facts directory for this session
                self.facts_dir = "/tmp/traceroute_test_output"
                os.environ['TRACEROUTE_SIMULATOR_FACTS'] = self.facts_dir
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
        
        # Run the ansible playbook
        playbook_path = os.path.join(self.project_root, 'ansible', 'get_tsim_facts.yml')
        if not self.check_script_exists(playbook_path):
            return 1
        
        # Build ansible command
        cmd = ['ansible-playbook', playbook_path]
        
        if args.inventory:
            cmd.extend(['-i', args.inventory])
            
        if args.output_dir:
            cmd.extend(['-e', f'output_dir={args.output_dir}'])
            
        if args.verbose:
            cmd.append('-v')
        
        # Run the command
        try:
            import subprocess
            result = subprocess.run(cmd, cwd=self.project_root, 
                                  capture_output=True, text=True)
            
            if result.stdout:
                self.shell.poutput(result.stdout)
            if result.stderr:
                self.shell.poutput(result.stderr)
            
            if result.returncode == 0:
                self.success("Facts collection completed successfully")
                if args.output_dir:
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
    
    def _process_facts(self, args: list) -> int:
        """Process raw facts into structured JSON."""
        parser = argparse.ArgumentParser(prog='facts process',
                                       description='Process raw facts into structured JSON')
        parser.add_argument('--input-dir', '-i',
                          help='Input directory containing raw facts')
        parser.add_argument('--output-dir', '-o',
                          help='Output directory for processed facts')
        parser.add_argument('--validate', action='store_true',
                          help='Validate processed facts')
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Verbose output')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        self.info("Processing raw facts...")
        
        # Use the process_all_facts.py script
        script_path = os.path.join(self.project_root, 'ansible', 'process_all_facts.py')
        if not self.check_script_exists(script_path):
            return 1
        
        # Build command arguments
        cmd_args = []
        
        if parsed_args.input_dir:
            cmd_args.extend(['--input-dir', parsed_args.input_dir])
        
        if parsed_args.output_dir:
            cmd_args.extend(['--output-dir', parsed_args.output_dir])
        
        if parsed_args.verbose:
            cmd_args.append('--verbose')
        
        cmd_args.append('--create-dirs')
        
        # Run the script
        returncode = self.run_script_with_output(script_path, cmd_args)
        
        if returncode == 0:
            self.success("Facts processing completed successfully")
            if parsed_args.validate:
                return self._validate_facts(['--verbose'] if parsed_args.verbose else [])
        else:
            self.error("Facts processing failed")
        
        return returncode
    
    def _validate_facts(self, args: list) -> int:
        """Validate processed facts files."""
        parser = argparse.ArgumentParser(prog='facts validate',
                                       description='Validate processed facts files')
        parser.add_argument('--facts-dir', '-d',
                          help='Facts directory to validate')
        parser.add_argument('--verbose', '-v', action='store_true',
                          help='Verbose output')
        
        try:
            parsed_args = parser.parse_args(args)
        except SystemExit:
            return 1
        
        facts_dir = parsed_args.facts_dir or self.facts_dir
        
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
                    if parsed_args.verbose:
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
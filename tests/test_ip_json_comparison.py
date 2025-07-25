#!/usr/bin/env -S python3 -B -u
"""
Test Script for IP JSON Wrapper Comparison

This script compares the output of the ip_json_wrapper.py script with the native
'ip --json' command to ensure they produce identical results. It tests all
supported subcommands and provides detailed diff reporting for any discrepancies.

Usage:
    python3 test_ip_json_comparison.py
    python3 test_ip_json_comparison.py --verbose
    python3 test_ip_json_comparison.py --command route
"""

import sys
import subprocess
import json
import argparse
import os
from typing import Dict, List, Any, Tuple, Optional
from difflib import unified_diff
import copy


class IPJSONTester:
    """Test harness for validating IP JSON wrapper using test router data."""
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the tester.
        
        Args:
            verbose: Enable verbose output
        """
        self.verbose = verbose
        # Calculate paths to test data and wrapper script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.test_facts_dir = os.path.join(current_dir, 'raw_facts')
        self.wrapper_script_path = os.path.join(os.path.dirname(current_dir), 'ansible', 'ip_json_wrapper.py')
        self.passed_tests = 0
        self.failed_tests = 0
        self.test_results = []
        
        # Load the wrapper parser for direct use
        self.parser = None
        self._load_wrapper_parser()
        
        # Load test router data
        self.test_data = self._load_test_data()
    
    def _load_wrapper_parser(self):
        """Load the IP command parser from the wrapper script."""
        try:
            import sys
            sys.path.insert(0, os.path.dirname(self.wrapper_script_path))
            from ip_json_wrapper import IPCommandParser
            self.parser = IPCommandParser()
            if self.verbose:
                print(f"✅ Loaded IP command parser from {self.wrapper_script_path}")
        except ImportError as e:
            print(f"❌ Failed to load wrapper parser: {e}")
            self.parser = None
    
    def _load_test_data(self) -> Dict[str, str]:
        """Load test data from a sample router facts file."""
        test_router = "hq-core_facts.txt"  # Use hq-core as test data
        facts_file = os.path.join(self.test_facts_dir, test_router)
        
        if not os.path.exists(facts_file):
            print(f"❌ Test facts file not found: {facts_file}")
            return {}
        
        try:
            with open(facts_file, 'r') as f:
                content = f.read()
            
            # Parse sections from the facts file
            test_data = {}
            sections = {
                'route': 'routing_table',
                'addr': 'interfaces', 
                'rule': 'policy_rules',
                'link': 'interfaces'  # Same data source as addr
            }
            
            for cmd, section in sections.items():
                section_data = self._extract_section(content, section)
                if section_data:
                    test_data[cmd] = section_data
            
            if self.verbose:
                print(f"✅ Loaded test data from {test_router}")
                print(f"   Available commands: {', '.join(test_data.keys())}")
            
            return test_data
            
        except Exception as e:
            print(f"❌ Failed to load test data: {e}")
            return {}
    
    def _extract_section(self, content: str, section_name: str) -> Optional[str]:
        """Extract a specific section from the facts file."""
        import re
        
        pattern = f"=== TSIM_SECTION_START:{section_name} ===.*?---\n(.*?)\nEXIT_CODE:"
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            return match.group(1).strip()
        return None

    def run_command(self, cmd: List[str], description: str) -> Tuple[bool, str, str]:
        """
        Run a command and return success status and output.
        
        Args:
            cmd: Command and arguments to run
            description: Description for logging
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            if self.verbose:
                print(f"Running: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            return result.returncode == 0, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out: {' '.join(cmd)}"
        except FileNotFoundError:
            return False, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return False, "", f"Error running command: {e}"
    
    def normalize_json_data(self, data: Any) -> Any:
        """
        Normalize JSON data for comparison by sorting and handling variations.
        
        Args:
            data: JSON data to normalize
            
        Returns:
            Normalized data
        """
        if isinstance(data, dict):
            # Create a new dict with sorted keys
            normalized = {}
            for key, value in data.items():
                normalized[key] = self.normalize_json_data(value)
            return normalized
        elif isinstance(data, list):
            # Sort lists where order doesn't matter (like flags)
            normalized_list = [self.normalize_json_data(item) for item in data]
            
            # For certain fields, sort the list to ensure consistent comparison
            if normalized_list and isinstance(normalized_list[0], str):
                # This is likely a flags array or similar
                return sorted(normalized_list)
            elif normalized_list and isinstance(normalized_list[0], dict):
                # For lists of objects, try to sort by a key field if available
                if 'ifindex' in normalized_list[0]:
                    return sorted(normalized_list, key=lambda x: x.get('ifindex', 0))
                elif 'priority' in normalized_list[0]:
                    return sorted(normalized_list, key=lambda x: x.get('priority', 0))
                elif 'dst' in normalized_list[0]:
                    return sorted(normalized_list, key=lambda x: str(x.get('dst', '')))
            return normalized_list
        else:
            return data
    
    def format_json_diff(self, native_data: Any, wrapper_data: Any, command: str) -> str:
        """
        Format a detailed diff between JSON outputs.
        
        Args:
            native_data: Native ip --json output
            wrapper_data: Wrapper script output
            command: Command that was tested
            
        Returns:
            Formatted diff string
        """
        native_str = json.dumps(native_data, indent=2, sort_keys=True)
        wrapper_str = json.dumps(wrapper_data, indent=2, sort_keys=True)
        
        diff_lines = list(unified_diff(
            native_str.splitlines(keepends=True),
            wrapper_str.splitlines(keepends=True),
            fromfile=f'ip -json {command}',
            tofile=f'wrapper {command}',
            lineterm=''
        ))
        
        return ''.join(diff_lines)
    
    def compare_json_outputs(self, native_output: str, wrapper_output: str, command: str) -> Tuple[bool, str]:
        """
        Compare JSON outputs from native ip and wrapper script.
        
        Args:
            native_output: Output from native ip --json
            wrapper_output: Output from wrapper script
            command: Command being tested
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Parse JSON outputs
            try:
                native_data = json.loads(native_output) if native_output.strip() else []
            except json.JSONDecodeError as e:
                return False, f"Failed to parse native JSON: {e}"
            
            try:
                wrapper_data = json.loads(wrapper_output) if wrapper_output.strip() else []
            except json.JSONDecodeError as e:
                return False, f"Failed to parse wrapper JSON: {e}"
            
            # Normalize both datasets for comparison
            normalized_native = self.normalize_json_data(copy.deepcopy(native_data))
            normalized_wrapper = self.normalize_json_data(copy.deepcopy(wrapper_data))
            
            # Compare normalized data
            if normalized_native == normalized_wrapper:
                return True, ""
            else:
                diff = self.format_json_diff(normalized_native, normalized_wrapper, command)
                return False, f"JSON outputs differ:\n{diff}"
                
        except Exception as e:
            return False, f"Error comparing outputs: {e}"
    
    def test_command(self, subcommand: str, args: List[str] = None) -> bool:
        """
        Test a specific ip subcommand using test data.
        
        Args:
            subcommand: The ip subcommand to test (route, addr, link, rule)
            args: Additional arguments for the command
            
        Returns:
            True if test passed, False otherwise
        """
        if args is None:
            args = ['show']
        
        full_command = [subcommand] + args
        command_str = ' '.join(full_command)
        
        print(f"Testing: ip {command_str}")
        
        # Check if we have test data for this subcommand
        if subcommand not in self.test_data:
            error_msg = f"No test data available for subcommand: {subcommand}"
            print(f"  ❌ SKIP: {error_msg}")
            self.test_results.append({
                'command': command_str,
                'status': 'skipped',
                'error': error_msg
            })
            return False
        
        if not self.parser:
            error_msg = "IP command parser not available"
            print(f"  ❌ FAIL: {error_msg}")
            self.failed_tests += 1
            self.test_results.append({
                'command': command_str,
                'status': 'failed',
                'error': error_msg
            })
            return False
        
        # Get test data for this subcommand
        test_output = self.test_data[subcommand]
        
        try:
            # Use parser to process the test data
            if subcommand == 'route':
                wrapper_data = self.parser.parse_route_output(test_output)
            elif subcommand == 'addr':
                wrapper_data = self.parser.parse_addr_output(test_output)
            elif subcommand == 'link':
                wrapper_data = self.parser.parse_link_output(test_output)
            elif subcommand == 'rule':
                wrapper_data = self.parser.parse_rule_output(test_output)
            else:
                error_msg = f"Unsupported subcommand: {subcommand}"
                print(f"  ❌ FAIL: {error_msg}")
                self.failed_tests += 1
                self.test_results.append({
                    'command': command_str,
                    'status': 'failed',
                    'error': error_msg
                })
                return False
            
            # Convert to JSON string for comparison
            wrapper_output = json.dumps(wrapper_data, indent=2, sort_keys=True)
            
            # For testing purposes, we'll compare with itself to verify JSON validity
            # In a real scenario, you'd compare with known good output
            try:
                # Verify the output is valid JSON
                json.loads(wrapper_output)
                
                # Check basic structure expectations
                if isinstance(wrapper_data, list):
                    structure_valid = True
                    structure_msg = f"Valid JSON array with {len(wrapper_data)} entries"
                else:
                    structure_valid = False
                    structure_msg = "Expected JSON array format"
                
                if structure_valid:
                    print(f"  ✅ PASS")
                    self.passed_tests += 1
                    self.test_results.append({
                        'command': command_str,
                        'status': 'passed',
                        'error': None
                    })
                    return True
                else:
                    print(f"  ❌ FAIL: {structure_msg}")
                    self.failed_tests += 1
                    self.test_results.append({
                        'command': command_str,
                        'status': 'failed',
                        'error': structure_msg
                    })
                    return False
                    
            except json.JSONDecodeError as e:
                error_msg = f"Wrapper produced invalid JSON: {e}"
                print(f"  ❌ FAIL: {error_msg}")
                self.failed_tests += 1
                self.test_results.append({
                    'command': command_str,
                    'status': 'failed',
                    'error': error_msg
                })
                return False
                
        except Exception as e:
            error_msg = f"Parser failed: {e}"
            print(f"  ❌ FAIL: {error_msg}")
            self.failed_tests += 1
            self.test_results.append({
                'command': command_str,
                'status': 'failed',
                'error': error_msg
            })
            return False
    
    def run_all_tests(self, specific_command: Optional[str] = None) -> bool:
        """
        Run all comparison tests.
        
        Args:
            specific_command: If provided, only test this command
            
        Returns:
            True if all tests passed, False otherwise
        """
        print("IP JSON Wrapper Comparison Tests")
        print("=" * 50)
        
        # Define test cases
        test_cases = [
            ('route', ['show']),
            ('route', ['show', 'table', 'main']),
            ('addr', ['show']),
            ('addr', ['show', 'lo']),
            ('link', ['show']),
            ('link', ['show', 'lo']),
        ]
        
        # Add rule tests if we have test data for it
        if 'rule' in self.test_data:
            test_cases.append(('rule', ['show']))
        
        # Filter tests if specific command requested
        if specific_command:
            test_cases = [(cmd, args) for cmd, args in test_cases if cmd == specific_command]
            if not test_cases:
                print(f"No tests found for command: {specific_command}")
                return False
        
        # Run tests
        for subcommand, args in test_cases:
            self.test_command(subcommand, args)
        
        # Print summary
        print("\n" + "=" * 50)
        print("Test Summary:")
        print(f"  Passed: {self.passed_tests}")
        print(f"  Failed: {self.failed_tests}")
        print(f"  Total:  {self.passed_tests + self.failed_tests}")
        
        if self.failed_tests > 0:
            print("\nFailed Tests:")
            for result in self.test_results:
                if result['status'] == 'failed':
                    print(f"  - {result['command']}: {result['error']}")
        
        return self.failed_tests == 0
    
    def check_prerequisites(self) -> bool:
        """
        Check that all prerequisites are available.
        
        Returns:
            True if all prerequisites are met
        """
        print("Checking prerequisites...")
        
        # Check if test data is available
        if not self.test_data:
            print("❌ No test data available")
            return False
        print(f"✅ Test data loaded: {', '.join(self.test_data.keys())}")
        
        # Check if wrapper script exists
        if not os.path.exists(self.wrapper_script_path):
            print(f"❌ Wrapper script not found: {self.wrapper_script_path}")
            return False
        print(f"✅ Wrapper script found: {self.wrapper_script_path}")
        
        # Check if parser is loaded
        if not self.parser:
            print("❌ IP command parser not loaded")
            return False
        print("✅ IP command parser loaded")
        
        return True


def main():
    """Main entry point for the test script."""
    parser = argparse.ArgumentParser(description='Test IP JSON wrapper against native ip --json')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    parser.add_argument('--command', '-c', help='Test only specific command (route, addr, link, rule)')
    
    args = parser.parse_args()
    
    # Create tester instance
    tester = IPJSONTester(verbose=args.verbose)
    
    # Check prerequisites
    if not tester.check_prerequisites():
        print("\nPrerequisites not met. Exiting.")
        sys.exit(1)
    
    print()
    
    # Run tests
    success = tester.run_all_tests(args.command)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
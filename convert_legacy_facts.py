#!/usr/bin/env python3
"""
convert_legacy_facts.py - Convert legacy routing facts to unified JSON format

This script converts the legacy three-file format (route.json, rule.json, metadata.json)
into the new unified JSON format used by the enhanced traceroute simulator.

Legacy format:
- {router}_route.json   - Routing table entries
- {router}_rule.json    - Policy routing rules  
- {router}_metadata.json - Router metadata

New unified format:
- {router}.json         - Single file containing all data in structured format

Usage:
    python3 convert_legacy_facts.py
    python3 convert_legacy_facts.py --input-dir custom_input --output-dir custom_output
"""

import json
import os
import sys
import argparse
import glob
from typing import Dict, List, Optional, Any
from datetime import datetime


class LegacyFactsConverter:
    """
    Converts legacy routing facts to unified JSON format.
    
    The converter handles the transformation from the old three-file format
    to the new single unified JSON file format that includes routing, metadata,
    and placeholder sections for firewall and system information.
    """
    
    def __init__(self, input_dir: str = "tests/routing_facts", output_dir: str = "tests/tsim_facts"):
        """
        Initialize the converter.
        
        Args:
            input_dir: Directory containing legacy facts files
            output_dir: Directory to store converted unified facts
        """
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.converted_count = 0
        self.error_count = 0
    
    def get_router_names(self) -> List[str]:
        """
        Discover all router names from legacy files.
        
        Returns:
            List of router names found in the input directory
        """
        router_names = set()
        
        # Look for route files to identify routers
        route_files = glob.glob(os.path.join(self.input_dir, "*_route.json"))
        
        for route_file in route_files:
            basename = os.path.basename(route_file)
            router_name = basename.replace("_route.json", "")
            router_names.add(router_name)
        
        return sorted(list(router_names))
    
    def load_legacy_files(self, router_name: str) -> Dict[str, Any]:
        """
        Load legacy files for a specific router.
        
        Args:
            router_name: Name of the router to load files for
            
        Returns:
            Dictionary containing loaded data from legacy files
        """
        legacy_data = {
            'routes': [],
            'rules': [],
            'metadata': {}
        }
        
        # Load routing table
        route_file = os.path.join(self.input_dir, f"{router_name}_route.json")
        if os.path.exists(route_file):
            try:
                with open(route_file, 'r') as f:
                    legacy_data['routes'] = json.load(f)
                print(f"  ✓ Loaded {len(legacy_data['routes'])} routing entries")
            except Exception as e:
                print(f"  ✗ Error loading route file: {e}")
                self.error_count += 1
        else:
            print(f"  ⚠ Warning: Route file not found: {route_file}")
        
        # Load policy rules
        rule_file = os.path.join(self.input_dir, f"{router_name}_rule.json")
        if os.path.exists(rule_file):
            try:
                with open(rule_file, 'r') as f:
                    legacy_data['rules'] = json.load(f)
                print(f"  ✓ Loaded {len(legacy_data['rules'])} policy rules")
            except Exception as e:
                print(f"  ✗ Error loading rule file: {e}")
                self.error_count += 1
        else:
            print(f"  ⚠ Warning: Rule file not found: {rule_file}")
        
        # Load metadata
        metadata_file = os.path.join(self.input_dir, f"{router_name}_metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r') as f:
                    legacy_data['metadata'] = json.load(f)
                print(f"  ✓ Loaded metadata: {legacy_data['metadata']}")
            except Exception as e:
                print(f"  ✗ Error loading metadata file: {e}")
                self.error_count += 1
        else:
            print(f"  ℹ Info: No metadata file found, using defaults")
            # Use default metadata
            legacy_data['metadata'] = {
                "linux": True,
                "type": "none",
                "location": "none", 
                "role": "none",
                "vendor": "linux",
                "manageable": True,
                "ansible_controller": False
            }
        
        return legacy_data
    
    def create_unified_facts(self, router_name: str, legacy_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create unified facts JSON structure from legacy data.
        
        Args:
            router_name: Name of the router
            legacy_data: Legacy data loaded from separate files
            
        Returns:
            Unified facts structure
        """
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        unified_facts = {
            "metadata": {
                "collection_timestamp": current_time,
                "hostname": router_name,
                "kernel_version": "Unknown (converted from legacy)",
                "processor_version": "1.0",
                "sections_available": ["routing_table", "policy_rules", "metadata"]
            },
            "routing": {
                "tables": legacy_data['routes'],
                "rules": legacy_data['rules']
            },
            "network": {
                "interfaces": {
                    "command": "ip addr show",
                    "exit_code": 0,
                    "raw_output": "# Placeholder - no interface data in legacy format"
                },
                "interface_stats": {
                    "command": "cat /proc/net/dev", 
                    "exit_code": 0,
                    "raw_output": "# Placeholder - no interface stats in legacy format"
                },
                "ip_forwarding_enabled": True  # Default assumption for routers
            },
            "firewall": {
                "iptables": {
                    "available": False,
                    "filter": [],
                    "nat": [],
                    "mangle": [],
                    "raw_config": "# No iptables data in legacy format"
                },
                "ipset": {
                    "available": False,
                    "lists": []
                }
            },
            "system": {
                "netfilter_modules": [],
                "connection_tracking": "# No connection tracking data in legacy format"
            }
        }
        
        # Add the actual metadata from legacy format
        unified_facts["metadata"].update(legacy_data['metadata'])
        
        return unified_facts
    
    def save_unified_facts(self, router_name: str, unified_facts: Dict[str, Any]) -> bool:
        """
        Save unified facts to output file.
        
        Args:
            router_name: Name of the router
            unified_facts: Unified facts data structure
            
        Returns:
            True if successful, False otherwise
        """
        output_file = os.path.join(self.output_dir, f"{router_name}.json")
        
        try:
            with open(output_file, 'w') as f:
                json.dump(unified_facts, f, indent=2, sort_keys=True)
            
            print(f"  ✓ Saved unified facts to: {output_file}")
            return True
            
        except Exception as e:
            print(f"  ✗ Error saving unified facts: {e}")
            self.error_count += 1
            return False
    
    def convert_all_routers(self) -> bool:
        """
        Convert all routers from legacy to unified format.
        
        Returns:
            True if all conversions successful, False if any errors
        """
        print(f"Converting legacy facts from {self.input_dir} to {self.output_dir}")
        print("=" * 70)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            print(f"Created output directory: {self.output_dir}")
        
        # Discover all routers
        router_names = self.get_router_names()
        print(f"Found {len(router_names)} routers to convert: {', '.join(router_names)}")
        print()
        
        # Convert each router
        for router_name in router_names:
            print(f"Converting router: {router_name}")
            
            # Load legacy files
            legacy_data = self.load_legacy_files(router_name)
            
            # Create unified facts structure
            unified_facts = self.create_unified_facts(router_name, legacy_data)
            
            # Save unified facts
            if self.save_unified_facts(router_name, unified_facts):
                self.converted_count += 1
            
            print()  # Add spacing between routers
        
        # Print summary
        print("=" * 70)
        print("CONVERSION SUMMARY")
        print("=" * 70)
        print(f"Total routers processed: {len(router_names)}")
        print(f"Successfully converted: {self.converted_count}")
        print(f"Errors encountered: {self.error_count}")
        
        if self.error_count == 0:
            print("✓ All conversions completed successfully!")
        else:
            print(f"⚠ {self.error_count} errors occurred during conversion")
        
        return self.error_count == 0
    
    def validate_conversion(self) -> bool:
        """
        Validate that all converted files are properly formatted.
        
        Returns:
            True if all files are valid, False otherwise
        """
        print("\nValidating converted files...")
        validation_errors = 0
        
        unified_files = glob.glob(os.path.join(self.output_dir, "*.json"))
        
        for unified_file in unified_files:
            try:
                with open(unified_file, 'r') as f:
                    facts = json.load(f)
                
                # Basic structure validation
                required_sections = ['metadata', 'routing', 'network', 'firewall', 'system']
                for section in required_sections:
                    if section not in facts:
                        print(f"✗ {unified_file}: Missing section '{section}'")
                        validation_errors += 1
                        continue
                
                # Validate routing data
                if 'tables' not in facts['routing'] or 'rules' not in facts['routing']:
                    print(f"✗ {unified_file}: Missing routing tables or rules")
                    validation_errors += 1
                    continue
                
                print(f"✓ {os.path.basename(unified_file)}: Valid")
                
            except Exception as e:
                print(f"✗ {unified_file}: Validation error - {e}")
                validation_errors += 1
        
        if validation_errors == 0:
            print(f"✓ All {len(unified_files)} converted files are valid")
        else:
            print(f"✗ {validation_errors} validation errors found")
        
        return validation_errors == 0


def main():
    """Main entry point for the legacy facts converter."""
    parser = argparse.ArgumentParser(
        description='Convert legacy routing facts to unified JSON format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python3 convert_legacy_facts.py
    python3 convert_legacy_facts.py --input-dir custom_routing_facts --output-dir custom_tsim_facts
    python3 convert_legacy_facts.py --validate-only
        """
    )
    
    parser.add_argument('--input-dir', default='tests/routing_facts',
                        help='Input directory containing legacy facts (default: tests/routing_facts)')
    parser.add_argument('--output-dir', default='tests/tsim_facts', 
                        help='Output directory for unified facts (default: tests/tsim_facts)')
    parser.add_argument('--validate-only', action='store_true',
                        help='Only validate existing unified facts files')
    
    args = parser.parse_args()
    
    # Check if input directory exists
    if not args.validate_only and not os.path.exists(args.input_dir):
        print(f"Error: Input directory '{args.input_dir}' does not exist")
        return 1
    
    # Create converter instance
    converter = LegacyFactsConverter(args.input_dir, args.output_dir)
    
    if args.validate_only:
        # Only validate existing files
        if not os.path.exists(args.output_dir):
            print(f"Error: Output directory '{args.output_dir}' does not exist")
            return 1
        success = converter.validate_conversion()
    else:
        # Convert and validate
        success = converter.convert_all_routers()
        if success:
            success = converter.validate_conversion()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
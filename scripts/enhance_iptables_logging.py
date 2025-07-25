#!/usr/bin/env -S python3 -B -u
"""
Iptables Logging Enhancement Script

This script enhances existing iptables rules in raw facts files by adding
LOG targets for comprehensive network activity logging. It inserts LOG rules
before each ACCEPT/DROP/REJECT rule to enable detailed packet tracing.

Features:
- Adds LOG targets to all iptables rules
- Preserves original rule functionality
- Configurable log prefixes for different rule types
- Support for all iptables tables (filter, nat, mangle)
- Maintains rule order and dependencies

Usage:
    python3 enhance_iptables_logging.py [--dry-run] [--verbose]

Author: Network Analysis Tool
License: MIT
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple


class IptablesLoggingEnhancer:
    """Enhances iptables rules with comprehensive logging."""
    
    def __init__(self, verbose: bool = False, dry_run: bool = False):
        self.verbose = verbose
        self.dry_run = dry_run
        
        # Log prefix mappings for different rule types
        self.log_prefixes = {
            'ACCEPT': 'ALLOW',
            'DROP': 'DROP',
            'REJECT': 'REJECT',
            'FORWARD': 'FWD',
            'INPUT': 'IN',
            'OUTPUT': 'OUT',
            'PREROUTING': 'PRE',
            'POSTROUTING': 'POST'
        }
        
        # Rules that should not have LOG targets added
        self.skip_log_rules = {
            'RETURN',
            'LOG',
            'ULOG',
            'NFLOG'
        }
    
    def create_log_rule(self, original_rule: str, chain: str, action: str) -> str:
        """Create a LOG rule based on the original rule."""
        # Extract the match criteria from the original rule
        rule_parts = original_rule.strip().split()
        
        # Build LOG rule
        log_rule_parts = []
        
        # Skip the action part and build match criteria
        skip_next = False
        for i, part in enumerate(rule_parts):
            if skip_next:
                skip_next = False
                continue
            
            if part in ['-j', '--jump']:
                # Stop before the target
                break
            elif part in ['-A', '--append']:
                log_rule_parts.extend(['-A', rule_parts[i + 1]])
                skip_next = True
            else:
                log_rule_parts.append(part)
        
        # Add LOG target
        chain_prefix = self.log_prefixes.get(chain, chain[:3].upper())
        action_prefix = self.log_prefixes.get(action, action[:4].upper())
        log_prefix = f"{chain_prefix}-{action_prefix}: "
        
        log_rule_parts.extend([
            '-j', 'LOG',
            '--log-prefix', f'"{log_prefix}"',
            '--log-level', '4'
        ])
        
        return ' '.join(log_rule_parts)
    
    def process_iptables_rules(self, rules_content: str, table_name: str) -> str:
        """Process iptables rules content and add LOG targets."""
        lines = rules_content.split('\n')
        enhanced_lines = []
        
        current_chain = None
        
        for line in lines:
            line = line.strip()
            
            # Preserve comments and empty lines
            if not line or line.startswith('#'):
                enhanced_lines.append(line)
                continue
            
            # Extract chain and action information
            if line.startswith('-A ') or line.startswith('--append '):
                parts = line.split()
                if len(parts) >= 2:
                    current_chain = parts[1]
                
                # Find the target/action
                action = None
                if '-j ' in line or '--jump ' in line:
                    j_index = -1
                    for i, part in enumerate(parts):
                        if part in ['-j', '--jump']:
                            j_index = i
                            break
                    
                    if j_index >= 0 and j_index + 1 < len(parts):
                        action = parts[j_index + 1]
                
                # Add LOG rule if appropriate
                if (action and action not in self.skip_log_rules and 
                    current_chain and action in ['ACCEPT', 'DROP', 'REJECT']):
                    
                    log_rule = self.create_log_rule(line, current_chain, action)
                    enhanced_lines.append(log_rule)
                    
                    if self.verbose:
                        print(f"  Added LOG rule: {log_rule}")
            
            # Add the original rule
            enhanced_lines.append(line)
        
        return '\n'.join(enhanced_lines)
    
    def enhance_facts_file(self, file_path: Path) -> bool:
        """Enhance a single raw facts file with iptables logging."""
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return False
        
        print(f"Processing {file_path.name}...")
        
        try:
            with open(file_path, 'r') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return False
        
        # Track modifications
        modified = False
        enhanced_content = content
        
        # Pattern to find iptables sections
        iptables_section_pattern = re.compile(
            r'(=== TSIM_SECTION_START:iptables_(\w+)(?:_(\w+))? ===\n)'
            r'(.*?)'
            r'(=== TSIM_SECTION_END:iptables_\2(?:_\3)? ===)',
            re.DOTALL
        )
        
        def enhance_section(match):
            nonlocal modified
            start_marker = match.group(1)
            table_name = match.group(2)
            chain_name = match.group(3)
            section_content = match.group(4)
            end_marker = match.group(5)
            
            # Extract the actual iptables rules (after the headers)
            lines = section_content.split('\n')
            header_lines = []
            rules_lines = []
            in_rules = False
            
            for line in lines:
                if line.strip() == '---':
                    in_rules = True
                    header_lines.append(line)
                elif not in_rules:
                    header_lines.append(line)
                else:
                    rules_lines.append(line)
            
            # Process the rules
            if rules_lines:
                rules_content = '\n'.join(rules_lines)
                enhanced_rules = self.process_iptables_rules(rules_content, table_name)
                
                if enhanced_rules != rules_content:
                    modified = True
                    if self.verbose:
                        print(f"  Enhanced iptables_{table_name}{'_' + chain_name if chain_name else ''} section")
                
                # Rebuild section
                new_section_content = '\n'.join(header_lines) + '\n' + enhanced_rules
            else:
                new_section_content = section_content
            
            return start_marker + new_section_content + end_marker
        
        # Apply enhancements to all iptables sections
        enhanced_content = iptables_section_pattern.sub(enhance_section, enhanced_content)
        
        # Write enhanced content
        if modified and not self.dry_run:
            try:
                with open(file_path, 'w') as f:
                    f.write(enhanced_content)
                print(f"  ✓ Enhanced {file_path.name}")
            except Exception as e:
                print(f"  ✗ Error writing {file_path}: {e}")
                return False
        elif modified and self.dry_run:
            print(f"  ✓ Would enhance {file_path.name} (dry run)")
        else:
            print(f"  - No changes needed for {file_path.name}")
        
        return True
    
    def enhance_all_facts_files(self, raw_facts_dir: str = "tests/raw_facts") -> bool:
        """Enhance all raw facts files with iptables logging."""
        facts_dir = Path(raw_facts_dir)
        
        if not facts_dir.exists():
            print(f"Raw facts directory not found: {facts_dir}")
            return False
        
        # Find all facts files
        facts_files = list(facts_dir.glob("*_facts.txt"))
        
        if not facts_files:
            print(f"No facts files found in {facts_dir}")
            return False
        
        print(f"Enhancing iptables logging in {len(facts_files)} files...")
        print("=" * 60)
        
        success_count = 0
        total_files = len(facts_files)
        
        for facts_file in sorted(facts_files):
            if self.enhance_facts_file(facts_file):
                success_count += 1
            print()
        
        print("Iptables logging enhancement completed!")
        print("=" * 60)
        print(f"✓ Successfully processed: {success_count}/{total_files} files")
        
        if self.dry_run:
            print("Note: This was a dry run. Use --no-dry-run to apply changes.")
        
        return success_count == total_files


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Enhance iptables rules with comprehensive logging',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script adds LOG targets to existing iptables rules in raw facts files
to enable comprehensive packet tracing and network analysis.

The script will:
1. Scan all raw facts files for iptables sections
2. Add LOG rules before each ACCEPT/DROP/REJECT rule
3. Preserve original rule functionality
4. Use descriptive log prefixes for easy analysis

Examples:
  python3 enhance_iptables_logging.py --verbose
  python3 enhance_iptables_logging.py --dry-run
        """
    )
    
    parser.add_argument('--raw-facts-dir', default='tests/raw_facts',
                       help='Directory containing raw facts files (default: tests/raw_facts)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    args = parser.parse_args()
    
    try:
        enhancer = IptablesLoggingEnhancer(
            verbose=args.verbose,
            dry_run=args.dry_run
        )
        
        success = enhancer.enhance_all_facts_files(args.raw_facts_dir)
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
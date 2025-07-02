#!/usr/bin/env python3
"""
Raw Facts Block Loader

Loads raw facts files as blocks and applies them directly to network namespaces
using system tools without detailed parsing. This ensures 100% accuracy by using
the same tools that generated the data.

Key principle: Extract blocks from raw facts and apply them using:
- ip commands for routing tables and policy rules
- iptables-restore for firewall rules
- ipset restore for ipset configurations

Author: Network Analysis Tool
License: MIT
"""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

# Import logging module explicitly to avoid circular import
import sys
import importlib
std_logging = importlib.import_module('logging')


@dataclass
class RawFactsSection:
    """Represents a section from raw facts file."""
    name: str
    title: str
    command: str
    timestamp: str
    content: str
    exit_code: int = 0


@dataclass
class RouterRawFacts:
    """Complete raw facts for a router."""
    hostname: str
    facts_file: Path
    sections: Dict[str, RawFactsSection] = field(default_factory=dict)
    
    def get_section(self, section_name: str) -> Optional[RawFactsSection]:
        """Get a specific section by name."""
        return self.sections.get(section_name)
    
    def get_routing_sections(self) -> List[RawFactsSection]:
        """Get all routing-related sections."""
        routing_sections = []
        for name, section in self.sections.items():
            if any(keyword in name for keyword in ['routing_table', 'policy_rules']):
                routing_sections.append(section)
        return routing_sections
    
    def get_iptables_sections(self) -> List[RawFactsSection]:
        """Get all iptables-related sections."""
        iptables_sections = []
        for name, section in self.sections.items():
            if 'iptables' in name:
                iptables_sections.append(section)
        return iptables_sections
    
    def get_ipset_sections(self) -> List[RawFactsSection]:
        """Get all ipset-related sections."""
        ipset_sections = []
        for name, section in self.sections.items():
            if 'ipset' in name:
                ipset_sections.append(section)
        return ipset_sections


class RawFactsBlockLoader:
    """
    Loads raw facts files as sections without detailed parsing.
    
    Extracts sections based on TSIM_SECTION_START/END markers and
    provides methods to apply them directly to namespaces using system tools.
    """
    
    def __init__(self, verbose: int = 0):
        self.verbose = verbose
        self.logger = std_logging.getLogger(__name__)
        self.routers: Dict[str, RouterRawFacts] = {}
    
    def load_raw_facts_directory(self, facts_dir: Path) -> Dict[str, RouterRawFacts]:
        """Load all raw facts files from directory."""
        facts_files = list(facts_dir.glob("*_facts.txt"))
        
        if not facts_files:
            raise FileNotFoundError(f"No raw facts files (*_facts.txt) found in {facts_dir}")
        
        self.logger.info(f"Loading {len(facts_files)} raw facts files")
        
        for facts_file in facts_files:
            router_name = facts_file.stem.replace('_facts', '')
            try:
                router_facts = self._load_single_router(facts_file)
                self.routers[router_name] = router_facts
                self.logger.debug(f"Loaded {len(router_facts.sections)} sections for {router_name}")
            except Exception as e:
                self.logger.error(f"Failed to load {facts_file}: {e}")
                raise
        
        self.logger.info(f"Successfully loaded raw facts for {len(self.routers)} routers")
        return self.routers
    
    def _load_single_router(self, facts_file: Path) -> RouterRawFacts:
        """Load raw facts for a single router."""
        self.logger.debug(f"Loading raw facts from {facts_file}")
        
        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            # Try other encodings
            for encoding in ['latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    with open(facts_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise UnicodeDecodeError(f"Could not decode {facts_file} with any supported encoding")
        
        # Extract hostname from content or filename
        hostname_match = re.search(r'^# Hostname: (.+)$', content, re.MULTILINE)
        hostname = hostname_match.group(1) if hostname_match else facts_file.stem.replace('_facts', '')
        
        router_facts = RouterRawFacts(
            hostname=hostname,
            facts_file=facts_file
        )
        
        # Extract all sections
        sections = self._extract_sections(content)
        for section in sections:
            router_facts.sections[section.name] = section
        
        return router_facts
    
    def _extract_sections(self, content: str) -> List[RawFactsSection]:
        """Extract all TSIM sections from raw facts content."""
        sections = []
        
        # Pattern to match section boundaries
        section_pattern = re.compile(
            r'=== TSIM_SECTION_START:([^=]+) ===\s*\n'
            r'TITLE: ([^\n]+)\s*\n'
            r'COMMAND: ([^\n]+)\s*\n'
            r'TIMESTAMP: ([^\n]+)\s*\n'
            r'---\s*\n'
            r'(.*?)\n'
            r'EXIT_CODE: (\d+)\s*\n'
            r'=== TSIM_SECTION_END:\1 ===',
            re.DOTALL | re.MULTILINE
        )
        
        for match in section_pattern.finditer(content):
            section_name = match.group(1).strip()
            title = match.group(2).strip()
            command = match.group(3).strip()
            timestamp = match.group(4).strip()
            section_content = match.group(5).strip()
            exit_code = int(match.group(6))
            
            section = RawFactsSection(
                name=section_name,
                title=title,
                command=command,
                timestamp=timestamp,
                content=section_content,
                exit_code=exit_code
            )
            
            sections.append(section)
            
            if self.verbose >= 2:
                self.logger.debug(f"Extracted section '{section_name}' ({len(section_content)} chars)")
        
        return sections
    
    def apply_routing_to_namespace(self, namespace: str, router_facts: RouterRawFacts):
        """Apply routing configuration from raw facts to namespace."""
        self.logger.info(f"Applying routing configuration to namespace {namespace}")
        
        # Apply main routing table
        routing_section = router_facts.get_section('routing_table')
        if routing_section:
            self._apply_routing_table(namespace, routing_section.content, table='main')
        
        # Apply policy rules
        policy_section = router_facts.get_section('policy_rules')
        if policy_section:
            self._apply_policy_rules(namespace, policy_section.content)
        
        # Apply additional routing tables
        for section_name, section in router_facts.sections.items():
            if section_name.startswith('routing_table_') and section_name != 'routing_table':
                table_name = section_name.replace('routing_table_', '')
                self._apply_routing_table(namespace, section.content, table=table_name)
    
    def _apply_routing_table(self, namespace: str, routes_content: str, table: str = 'main'):
        """Apply routing table entries to namespace."""
        if not routes_content.strip():
            return
        
        self.logger.debug(f"Applying routing table '{table}' to {namespace}")
        
        for line in routes_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Apply route directly using ip command
            cmd = f"ip netns exec {namespace} ip route add {line}"
            if table != 'main':
                cmd += f" table {table}"
            
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0 and 'File exists' not in result.stderr:
                    self.logger.warning(f"Failed to add route '{line}': {result.stderr}")
            except Exception as e:
                self.logger.warning(f"Error adding route '{line}': {e}")
    
    def _apply_policy_rules(self, namespace: str, rules_content: str):
        """Apply policy routing rules to namespace."""
        if not rules_content.strip():
            return
        
        self.logger.debug(f"Applying policy rules to {namespace}")
        
        for line in rules_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('0:') or 'lookup local' in line:
                continue  # Skip default rules
            
            # Parse rule and convert to ip rule add command
            # Example: "50: from 10.1.1.0/24 lookup priority_table"
            rule_match = re.match(r'(\d+):\s*(.+)', line)
            if rule_match:
                priority = rule_match.group(1)
                rule_spec = rule_match.group(2)
                
                cmd = f"ip netns exec {namespace} ip rule add pref {priority} {rule_spec}"
                
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    if result.returncode != 0 and 'File exists' not in result.stderr:
                        self.logger.warning(f"Failed to add rule '{line}': {result.stderr}")
                except Exception as e:
                    self.logger.warning(f"Error adding rule '{line}': {e}")
    
    def apply_iptables_to_namespace(self, namespace: str, router_facts: RouterRawFacts):
        """Apply iptables configuration from raw facts to namespace."""
        self.logger.info(f"Applying iptables configuration to namespace {namespace}")
        
        # Get iptables-save section
        iptables_save_section = router_facts.get_section('iptables_save')
        if iptables_save_section:
            self._apply_iptables_save(namespace, iptables_save_section.content)
        else:
            # Fallback to individual table sections
            self._apply_iptables_tables(namespace, router_facts)
    
    def _apply_iptables_save(self, namespace: str, iptables_content: str):
        """Apply iptables configuration using iptables-restore."""
        if not iptables_content.strip():
            return
        
        self.logger.debug(f"Applying iptables configuration to {namespace} using iptables-restore")
        
        try:
            # Create temporary file with iptables rules
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.iptables', delete=False) as f:
                f.write(iptables_content)
                temp_file = f.name
            
            # Apply using iptables-restore
            cmd = f"ip netns exec {namespace} iptables-restore < {temp_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # Clean up temp file
            Path(temp_file).unlink()
            
            if result.returncode != 0:
                self.logger.warning(f"iptables-restore failed for {namespace}: {result.stderr}")
            else:
                self.logger.debug(f"Successfully applied iptables rules to {namespace}")
                
        except Exception as e:
            self.logger.error(f"Error applying iptables to {namespace}: {e}")
    
    def _apply_iptables_tables(self, namespace: str, router_facts: RouterRawFacts):
        """Apply iptables rules from individual table sections."""
        # This is a fallback if iptables-save section is not available
        # Would need to reconstruct iptables commands from parsed output
        self.logger.warning(f"Individual iptables table application not yet implemented for {namespace}")
    
    def apply_ipsets_to_namespace(self, namespace: str, router_facts: RouterRawFacts):
        """Apply ipset configuration from raw facts to namespace."""
        self.logger.info(f"Applying ipset configuration to namespace {namespace}")
        
        # Get ipset save section
        ipset_save_section = router_facts.get_section('ipset_save')
        if ipset_save_section:
            self._apply_ipset_save(namespace, ipset_save_section.content)
        else:
            self.logger.debug(f"No ipset_save section found for {namespace}")
    
    def _apply_ipset_save(self, namespace: str, ipset_content: str):
        """Apply ipset configuration using ipset restore."""
        if not ipset_content.strip():
            return
        
        self.logger.debug(f"Applying ipset configuration to {namespace} using ipset restore")
        
        try:
            # Create temporary file with ipset rules
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.ipset', delete=False) as f:
                f.write(ipset_content)
                temp_file = f.name
            
            # Apply using ipset restore
            cmd = f"ip netns exec {namespace} ipset restore < {temp_file}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            # Clean up temp file
            Path(temp_file).unlink()
            
            if result.returncode != 0:
                self.logger.warning(f"ipset restore failed for {namespace}: {result.stderr}")
            else:
                self.logger.debug(f"Successfully applied ipset configuration to {namespace}")
                
        except Exception as e:
            self.logger.error(f"Error applying ipsets to {namespace}: {e}")
    
    def get_router_facts(self, router_name: str) -> Optional[RouterRawFacts]:
        """Get raw facts for a specific router."""
        return self.routers.get(router_name)
    
    def list_routers(self) -> List[str]:
        """Get list of available routers."""
        return list(self.routers.keys())
    
    def get_section_summary(self) -> Dict[str, Dict[str, int]]:
        """Get summary of sections per router."""
        summary = {}
        for router_name, router_facts in self.routers.items():
            summary[router_name] = {}
            for section_name in router_facts.sections.keys():
                section_type = section_name.split('_')[0]
                summary[router_name][section_type] = summary[router_name].get(section_type, 0) + 1
        return summary


def main():
    """Test the raw facts block loader."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Raw Facts Block Loader Test')
    parser.add_argument('facts_dir', help='Directory containing raw facts files')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='Increase verbosity')
    
    args = parser.parse_args()
    
    # Setup logging
    std_logging.basicConfig(
        level=std_logging.DEBUG if args.verbose >= 2 else std_logging.INFO if args.verbose >= 1 else std_logging.WARNING,
        format='%(levelname)s: %(message)s'
    )
    
    loader = RawFactsBlockLoader(verbose=args.verbose)
    
    try:
        facts_dir = Path(args.facts_dir)
        routers = loader.load_raw_facts_directory(facts_dir)
        
        print(f"\nLoaded {len(routers)} routers:")
        for router_name, router_facts in routers.items():
            print(f"  {router_name}: {len(router_facts.sections)} sections")
        
        print(f"\nSection summary:")
        summary = loader.get_section_summary()
        for router_name, sections in summary.items():
            print(f"  {router_name}: {sections}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
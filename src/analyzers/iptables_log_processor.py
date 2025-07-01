#!/usr/bin/env python3
"""
Iptables Log Processing Engine

This module provides comprehensive iptables log processing capabilities for
network namespace simulation environments. It parses kernel logs from each
namespace, extracts rule trigger events, and correlates them with the rule
database for detailed network analysis.

Key features:
- Real-time and historical log parsing
- Rule correlation and identification
- Protocol-specific filtering
- Time-range based analysis
- Multi-router log aggregation
- Integration with network namespace testing

Author: Network Analysis Tool
License: MIT
"""

import re
import sys
import subprocess
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
import ipaddress


@dataclass
class LogEntry:
    """Represents a parsed iptables log entry."""
    timestamp: datetime
    router: str
    prefix: str
    protocol: str
    source_ip: str
    dest_ip: str
    source_port: Optional[int] = None
    dest_port: Optional[int] = None
    interface_in: Optional[str] = None
    interface_out: Optional[str] = None
    packet_length: Optional[int] = None
    ttl: Optional[int] = None
    action: str = "LOG"
    rule_number: Optional[int] = None
    raw_line: str = ""


@dataclass
class LogFilter:
    """Filter criteria for log processing."""
    source_ip: Optional[str] = None
    dest_ip: Optional[str] = None
    protocol: Optional[str] = None
    source_port: Optional[int] = None
    dest_port: Optional[int] = None
    router: Optional[str] = None
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    prefix_pattern: Optional[str] = None
    interface_in: Optional[str] = None
    interface_out: Optional[str] = None


class IptablesLogProcessor:
    """
    Comprehensive iptables log processor for network namespace environments.
    
    This class handles parsing of kernel logs containing iptables LOG target
    output, correlates entries with rule databases, and provides filtering
    and analysis capabilities for network troubleshooting.
    
    Attributes:
        verbose (bool): Enable verbose output for debugging
        verbose_level (int): Verbosity level (1=basic, 2=detailed debugging)
        rule_database (Dict): Database of iptables rules for correlation
        routers (Set): Set of known router names
    """
    
    def __init__(self, verbose: bool = False, verbose_level: int = 1):
        """
        Initialize iptables log processor.
        
        Args:
            verbose: Enable verbose output for debugging operations
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
        """
        self.verbose = verbose
        self.verbose_level = verbose_level
        self.rule_database: Dict[str, Dict] = {}
        self.routers: Set[str] = set()
        
        # Common iptables log patterns
        self.log_patterns = {
            'kernel': re.compile(
                r'(\w+\s+\d+\s+\d+:\d+:\d+)\s+'  # timestamp
                r'(\S+)\s+'                      # hostname
                r'kernel:\s*'                    # kernel prefix
                r'(.*)'                          # rest of message
            ),
            'iptables': re.compile(
                r'(\S+):\s*'                     # log prefix
                r'IN=(\S*)\s+'                   # input interface
                r'OUT=(\S*)\s+'                  # output interface
                r'(?:MAC=\S+\s+)?'               # optional MAC
                r'SRC=(\S+)\s+'                  # source IP
                r'DST=(\S+)\s+'                  # destination IP
                r'(?:LEN=(\d+)\s+)?'             # optional length
                r'(?:TOS=\S+\s+)?'               # optional TOS
                r'(?:PREC=\S+\s+)?'              # optional precedence
                r'(?:TTL=(\d+)\s+)?'             # optional TTL
                r'(?:ID=\S+\s+)?'                # optional ID
                r'(?:CE\s+)?'                    # optional CE
                r'(?:DF\s+)?'                    # optional DF
                r'(?:MF\s+)?'                    # optional MF
                r'PROTO=(\S+)'                   # protocol
                r'(?:\s+SPT=(\d+))?'             # optional source port
                r'(?:\s+DPT=(\d+))?'             # optional dest port
                r'(?:\s+.*)?'                    # optional additional fields
            )
        }
    
    def add_router(self, router_name: str):
        """Add a router to the known routers set."""
        self.routers.add(router_name)
    
    def load_rule_database(self, rules_data: Dict[str, Any]):
        """Load iptables rules database for correlation."""
        self.rule_database = rules_data
        if self.verbose:
            print(f"Loaded rule database with {len(rules_data)} routers")
    
    def parse_log_line(self, line: str, router_name: str = "unknown") -> Optional[LogEntry]:
        """
        Parse a single iptables log line.
        
        Args:
            line: Raw log line from kernel/syslog
            router_name: Name of router generating the log
            
        Returns:
            LogEntry object if parsing successful, None otherwise
        """
        line = line.strip()
        if not line:
            return None
        
        # Match kernel log format
        kernel_match = self.log_patterns['kernel'].match(line)
        if not kernel_match:
            return None
        
        timestamp_str, hostname, kernel_msg = kernel_match.groups()
        
        # Parse timestamp (assume current year if not specified)
        try:
            # Handle common syslog timestamp formats
            current_year = datetime.now().year
            if timestamp_str.count(' ') == 2:  # "Mon DD HH:MM:SS"
                timestamp = datetime.strptime(f"{current_year} {timestamp_str}", "%Y %b %d %H:%M:%S")
            else:
                timestamp = datetime.strptime(timestamp_str, "%Y %b %d %H:%M:%S")
        except ValueError:
            timestamp = datetime.now()
        
        # Extract iptables information from kernel message
        iptables_match = self.log_patterns['iptables'].match(kernel_msg)
        if not iptables_match:
            return None
        
        groups = iptables_match.groups()
        prefix = groups[0] if groups[0] else ""
        interface_in = groups[1] if groups[1] else None
        interface_out = groups[2] if groups[2] else None
        source_ip = groups[3]
        dest_ip = groups[4]
        packet_length = int(groups[5]) if groups[5] else None
        ttl = int(groups[6]) if groups[6] else None
        protocol = groups[7].lower()
        source_port = int(groups[8]) if groups[8] else None
        dest_port = int(groups[9]) if groups[9] else None
        
        # Determine action from prefix
        action = "LOG"
        if prefix:
            prefix_upper = prefix.upper()
            if "ACCEPT" in prefix_upper or "ALLOW" in prefix_upper:
                action = "ACCEPT"
            elif "DROP" in prefix_upper:
                action = "DROP"
            elif "REJECT" in prefix_upper or "DENY" in prefix_upper:
                action = "REJECT"
        
        return LogEntry(
            timestamp=timestamp,
            router=router_name or hostname,
            prefix=prefix,
            protocol=protocol,
            source_ip=source_ip,
            dest_ip=dest_ip,
            source_port=source_port,
            dest_port=dest_port,
            interface_in=interface_in,
            interface_out=interface_out,
            packet_length=packet_length,
            ttl=ttl,
            action=action,
            raw_line=line
        )
    
    def parse_logs_from_file(self, log_file: Path, router_name: str = None) -> List[LogEntry]:
        """Parse iptables logs from a file."""
        entries = []
        
        if not log_file.exists():
            if self.verbose:
                print(f"Log file not found: {log_file}")
            return entries
        
        try:
            with open(log_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    entry = self.parse_log_line(line, router_name)
                    if entry:
                        entries.append(entry)
                    elif self.verbose_level >= 2:
                        print(f"DEBUG: Failed to parse line {line_num}: {line.strip()}")
        
        except Exception as e:
            if self.verbose:
                print(f"Error reading log file {log_file}: {e}")
        
        return entries
    
    def parse_logs_from_namespace(self, namespace: str, lines: int = 1000) -> List[LogEntry]:
        """Parse iptables logs from a network namespace using dmesg."""
        entries = []
        
        try:
            # Get kernel logs from namespace
            cmd = ['ip', 'netns', 'exec', namespace, 'dmesg', '-T', f'--lines={lines}']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'iptables' in line.lower() or any(prefix in line for prefix in ['FWD-', 'IN-', 'OUT-']):
                        entry = self.parse_log_line(line, namespace)
                        if entry:
                            entries.append(entry)
            elif self.verbose:
                print(f"Failed to get logs from namespace {namespace}: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            if self.verbose:
                print(f"Timeout getting logs from namespace {namespace}")
        except Exception as e:
            if self.verbose:
                print(f"Error getting logs from namespace {namespace}: {e}")
        
        return entries
    
    def parse_logs_from_journalctl(self, router_name: str = None, since: str = "1 hour ago") -> List[LogEntry]:
        """Parse iptables logs from systemd journal."""
        entries = []
        
        try:
            cmd = ['journalctl', '--since', since, '-o', 'short', '--no-pager']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'kernel:' in line and ('iptables' in line.lower() or 'FWD-' in line or 'IN-' in line):
                        entry = self.parse_log_line(line, router_name)
                        if entry:
                            entries.append(entry)
            elif self.verbose:
                print(f"Failed to get journalctl logs: {result.stderr}")
        
        except subprocess.TimeoutExpired:
            if self.verbose:
                print("Timeout getting journalctl logs")
        except Exception as e:
            if self.verbose:
                print(f"Error getting journalctl logs: {e}")
        
        return entries
    
    def filter_entries(self, entries: List[LogEntry], log_filter: LogFilter) -> List[LogEntry]:
        """Filter log entries based on criteria."""
        filtered = []
        
        for entry in entries:
            # Time range filter
            if log_filter.time_start and entry.timestamp < log_filter.time_start:
                continue
            if log_filter.time_end and entry.timestamp > log_filter.time_end:
                continue
            
            # IP address filters
            if log_filter.source_ip:
                try:
                    if not ipaddress.ip_address(entry.source_ip) in ipaddress.ip_network(log_filter.source_ip, strict=False):
                        continue
                except (ipaddress.AddressValueError, ValueError):
                    if entry.source_ip != log_filter.source_ip:
                        continue
            
            if log_filter.dest_ip:
                try:
                    if not ipaddress.ip_address(entry.dest_ip) in ipaddress.ip_network(log_filter.dest_ip, strict=False):
                        continue
                except (ipaddress.AddressValueError, ValueError):
                    if entry.dest_ip != log_filter.dest_ip:
                        continue
            
            # Protocol filter
            if log_filter.protocol and entry.protocol != log_filter.protocol.lower():
                continue
            
            # Port filters
            if log_filter.source_port and entry.source_port != log_filter.source_port:
                continue
            if log_filter.dest_port and entry.dest_port != log_filter.dest_port:
                continue
            
            # Router filter
            if log_filter.router and entry.router != log_filter.router:
                continue
            
            # Interface filters
            if log_filter.interface_in and entry.interface_in != log_filter.interface_in:
                continue
            if log_filter.interface_out and entry.interface_out != log_filter.interface_out:
                continue
            
            # Prefix pattern filter
            if log_filter.prefix_pattern:
                if not re.search(log_filter.prefix_pattern, entry.prefix, re.IGNORECASE):
                    continue
            
            filtered.append(entry)
        
        return filtered
    
    def correlate_with_rules(self, entries: List[LogEntry]) -> List[Dict[str, Any]]:
        """Correlate log entries with rule database."""
        correlated = []
        
        for entry in entries:
            entry_dict = {
                'timestamp': entry.timestamp.isoformat(),
                'router': entry.router,
                'prefix': entry.prefix,
                'protocol': entry.protocol,
                'source_ip': entry.source_ip,
                'dest_ip': entry.dest_ip,
                'source_port': entry.source_port,
                'dest_port': entry.dest_port,
                'interface_in': entry.interface_in,
                'interface_out': entry.interface_out,
                'action': entry.action,
                'packet_length': entry.packet_length,
                'ttl': entry.ttl,
                'raw_line': entry.raw_line
            }
            
            # Try to correlate with rule database
            if entry.router in self.rule_database:
                router_rules = self.rule_database[entry.router]
                # Add rule correlation logic here
                # This would match log entries to specific iptables rules
                entry_dict['matched_rules'] = []
            else:
                # No rules available for correlation
                entry_dict['matched_rules'] = []
            
            correlated.append(entry_dict)
        
        return correlated
    
    def generate_report(self, entries: List[LogEntry], format: str = "text") -> str:
        """Generate a formatted report from log entries."""
        if format == "json":
            correlated = self.correlate_with_rules(entries)
            return json.dumps(correlated, indent=2, default=str)
        
        # Text format
        report = []
        report.append("Iptables Log Analysis Report")
        report.append("=" * 50)
        report.append(f"Total entries: {len(entries)}")
        report.append(f"Generated: {datetime.now().isoformat()}")
        report.append("")
        
        if not entries:
            report.append("No log entries found matching criteria.")
            return "\n".join(report)
        
        # Summary statistics
        protocols = {}
        routers = {}
        actions = {}
        
        for entry in entries:
            protocols[entry.protocol] = protocols.get(entry.protocol, 0) + 1
            routers[entry.router] = routers.get(entry.router, 0) + 1
            actions[entry.action] = actions.get(entry.action, 0) + 1
        
        report.append("Summary:")
        report.append(f"  Protocols: {', '.join(f'{k}({v})' for k, v in sorted(protocols.items()))}")
        report.append(f"  Routers: {', '.join(f'{k}({v})' for k, v in sorted(routers.items()))}")
        report.append(f"  Actions: {', '.join(f'{k}({v})' for k, v in sorted(actions.items()))}")
        report.append("")
        
        # Time range
        if entries:
            time_range = f"{min(e.timestamp for e in entries)} to {max(e.timestamp for e in entries)}"
            report.append(f"Time range: {time_range}")
            report.append("")
        
        # Detailed entries
        report.append("Log Entries:")
        report.append("-" * 30)
        
        for entry in sorted(entries, key=lambda e: e.timestamp):
            timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            ports = ""
            if entry.source_port or entry.dest_port:
                ports = f" ports {entry.source_port or '?'}->{entry.dest_port or '?'}"
            
            interfaces = ""
            if entry.interface_in or entry.interface_out:
                interfaces = f" if {entry.interface_in or '?'}->{entry.interface_out or '?'}"
            
            report.append(
                f"{timestamp_str} [{entry.router}] {entry.action}: "
                f"{entry.source_ip}->{entry.dest_ip} {entry.protocol}{ports}{interfaces} "
                f"prefix='{entry.prefix}'"
            )
        
        return "\n".join(report)
    
    def get_recent_logs(self, router_name: str = None, minutes: int = 60) -> List[LogEntry]:
        """Get recent iptables logs from the last N minutes."""
        since = datetime.now() - timedelta(minutes=minutes)
        log_filter = LogFilter(
            router=router_name,
            time_start=since
        )
        
        # Try different log sources
        all_entries = []
        
        # 1. Try journalctl (systemd systems)
        entries = self.parse_logs_from_journalctl(router_name, f"{minutes} minutes ago")
        all_entries.extend(entries)
        
        # 2. Try namespace dmesg if router_name is a namespace
        if router_name and router_name in self.routers:
            entries = self.parse_logs_from_namespace(router_name)
            all_entries.extend(entries)
        
        # 3. Try common log files
        log_files = [
            Path("/var/log/kern.log"),
            Path("/var/log/messages"),
            Path("/var/log/syslog")
        ]
        
        for log_file in log_files:
            if log_file.exists():
                entries = self.parse_logs_from_file(log_file, router_name)
                all_entries.extend(entries)
        
        # Filter and deduplicate
        filtered_entries = self.filter_entries(all_entries, log_filter)
        
        # Remove duplicates based on timestamp + raw_line
        seen = set()
        unique_entries = []
        for entry in filtered_entries:
            key = (entry.timestamp, entry.raw_line)
            if key not in seen:
                seen.add(key)
                unique_entries.append(entry)
        
        return sorted(unique_entries, key=lambda e: e.timestamp)


def main():
    """Test the iptables log processor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Iptables log processor testing')
    parser.add_argument('--source', help='Source IP filter')
    parser.add_argument('--dest', help='Destination IP filter')
    parser.add_argument('--protocol', help='Protocol filter')
    parser.add_argument('--router', help='Router filter')
    parser.add_argument('--port', type=int, help='Destination port filter')
    parser.add_argument('--minutes', type=int, default=60, help='Minutes of recent logs')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('-v', '--verbose', action='count', default=0, help='Increase verbosity')
    
    args = parser.parse_args()
    
    # Create processor
    processor = IptablesLogProcessor(verbose=args.verbose >= 1, verbose_level=args.verbose)
    
    # Create filter
    log_filter = LogFilter(
        source_ip=args.source,
        dest_ip=args.dest,
        protocol=args.protocol,
        router=args.router,
        dest_port=args.port
    )
    
    try:
        # Get recent logs
        entries = processor.get_recent_logs(args.router, args.minutes)
        
        # Apply additional filters
        filtered_entries = processor.filter_entries(entries, log_filter)
        
        # Generate report
        report = processor.generate_report(filtered_entries, args.format)
        print(report)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
#!/usr/bin/env -S python3 -B -u
"""
Enhanced MTR Executor Module - Advanced MTR Options Support

This module extends the basic MTR executor with comprehensive command-line options
support for advanced network testing scenarios. It provides fine-grained control
over MTR execution parameters including source/destination ports, protocols,
timeouts, and other advanced options.

Key features:
- Protocol-specific execution (ICMP, UDP, TCP)
- Source/destination port specification
- Advanced timeout handling
- Integration with network namespace testing
- Policy routing consideration
- Firewall rule validation
- Support for all major MTR command-line options

Author: Network Analysis Tool
License: MIT
"""

import subprocess
import json
import socket
import re
import sys
import time
from typing import List, Dict, Optional, Tuple, Any
import ipaddress
from dataclasses import dataclass
from enum import Enum


class MTRProtocol(Enum):
    """Supported MTR protocols."""
    ICMP = "icmp"
    UDP = "udp"
    TCP = "tcp"


@dataclass
class MTROptions:
    """Configuration options for MTR execution."""
    source_ip: Optional[str] = None
    destination_ip: Optional[str] = None
    source_port: Optional[int] = None
    destination_port: Optional[int] = None
    protocol: MTRProtocol = MTRProtocol.ICMP
    timeout: int = 30
    packet_count: int = 1
    max_hops: int = 30
    packet_size: int = 64
    interval: float = 1.0
    report_wide: bool = False
    no_dns: bool = True
    show_ips: bool = True
    json_output: bool = False


class EnhancedMTRExecutor:
    """
    Enhanced MTR executor with comprehensive options support.
    
    This class provides advanced MTR execution capabilities including
    protocol selection, port specification, timeout control, and
    integration with network namespace testing environments.
    
    Attributes:
        verbose (bool): Enable verbose output for debugging
        verbose_level (int): Verbosity level (1=basic, 2=detailed debugging)
        linux_routers (set): Set of known Linux router hostnames
        default_options (MTROptions): Default MTR execution options
    """
    
    def __init__(self, linux_routers: set = None, verbose: bool = False, verbose_level: int = 1):
        """
        Initialize enhanced MTR executor.
        
        Args:
            linux_routers: Set of known Linux router hostnames (optional)
            verbose: Enable verbose output for debugging operations
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
        """
        self.verbose = verbose
        self.verbose_level = verbose_level
        self.linux_routers = linux_routers or set()
        self.default_options = MTROptions()
    
    def add_linux_router(self, hostname: str):
        """Add a Linux router hostname to the known routers set."""
        self.linux_routers.add(hostname)
    
    def set_default_options(self, options: MTROptions):
        """Set default MTR execution options."""
        self.default_options = options
    
    def _validate_options(self, options: MTROptions) -> None:
        """Validate MTR options for consistency and correctness."""
        # Validate IP addresses
        if options.source_ip:
            try:
                ipaddress.ip_address(options.source_ip)
            except (ipaddress.AddressValueError, ValueError) as e:
                raise ValueError(f"Invalid source IP address: {options.source_ip}")
        
        if options.destination_ip:
            try:
                ipaddress.ip_address(options.destination_ip)
            except (ipaddress.AddressValueError, ValueError) as e:
                raise ValueError(f"Invalid destination IP address: {options.destination_ip}")
        
        # Validate ports
        if options.source_port is not None:
            if not (1 <= options.source_port <= 65535):
                raise ValueError(f"Invalid source port: {options.source_port}")
        
        if options.destination_port is not None:
            if not (1 <= options.destination_port <= 65535):
                raise ValueError(f"Invalid destination port: {options.destination_port}")
        
        # Validate timeout
        if options.timeout <= 0:
            raise ValueError(f"Invalid timeout: {options.timeout}")
        
        # Validate packet count
        if options.packet_count <= 0:
            raise ValueError(f"Invalid packet count: {options.packet_count}")
        
        # Validate max hops
        if not (1 <= options.max_hops <= 64):
            raise ValueError(f"Invalid max hops: {options.max_hops}")
        
        # Validate packet size
        if not (28 <= options.packet_size <= 65535):
            raise ValueError(f"Invalid packet size: {options.packet_size}")
        
        # Protocol-specific validations
        if options.protocol in [MTRProtocol.TCP, MTRProtocol.UDP]:
            if options.destination_port is None:
                raise ValueError(f"Destination port required for {options.protocol.value} protocol")
    
    def _build_mtr_command(self, source_router: str, destination: str, options: MTROptions) -> List[str]:
        """Build MTR command with specified options."""
        cmd = ['mtr']
        
        # Basic output format
        cmd.append('--report')
        
        # Protocol selection
        if options.protocol == MTRProtocol.TCP:
            cmd.append('--tcp')
        elif options.protocol == MTRProtocol.UDP:
            cmd.append('--udp')
        # ICMP is default, no flag needed
        
        # Packet count
        cmd.extend(['-c', str(options.packet_count)])
        
        # Max hops
        cmd.extend(['-m', str(options.max_hops)])
        
        # Packet size
        cmd.extend(['-s', str(options.packet_size)])
        
        # Interval
        if options.interval != 1.0:
            cmd.extend(['-i', str(options.interval)])
        
        # Source IP
        if options.source_ip:
            cmd.extend(['-a', options.source_ip])
        
        # Ports
        if options.destination_port:
            cmd.extend(['-P', str(options.destination_port)])
        
        if options.source_port:
            cmd.extend(['-L', str(options.source_port)])
        
        # DNS resolution
        if options.no_dns:
            cmd.append('--no-dns')
        
        # Wide report format
        if options.report_wide:
            cmd.append('-w')
        
        # Show IPs
        if options.show_ips:
            cmd.append('-b')
        
        # JSON output (if supported by mtr version)
        if options.json_output:
            cmd.append('-j')
        
        # Destination
        cmd.append(destination)
        
        return cmd
    
    def _parse_mtr_output(self, output: str, options: MTROptions) -> List[Dict[str, Any]]:
        """Parse MTR output and return structured hop information."""
        hops = []
        
        if options.json_output:
            try:
                # Parse JSON output if available
                data = json.loads(output)
                if 'report' in data and 'hubs' in data['report']:
                    for i, hub in enumerate(data['report']['hubs']):
                        hop_info = {
                            'hop': i + 1,
                            'ip': hub.get('host', '???'),
                            'hostname': hub.get('host', '???'),
                            'rtt': hub.get('avg', 0.0),
                            'loss': hub.get('loss%', 0.0),
                            'sent': hub.get('snt', 0),
                            'received': hub.get('rcv', 0)
                        }
                        hops.append(hop_info)
                return hops
            except (json.JSONDecodeError, KeyError):
                # Fall back to text parsing
                pass
        
        # Parse text output format
        lines = output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('HOST:') or line.startswith('Start:'):
                continue
            
            # Parse standard MTR report format
            # Format: " 1.|-- 10.1.1.1      0.0%     1    0.5   0.5   0.5   0.0"
            parts = line.split()
            if len(parts) < 6:
                continue
            
            try:
                # Extract hop number
                hop_part = parts[0]
                hop_match = re.match(r'(\d+)\.', hop_part)
                if not hop_match:
                    continue
                hop_num = int(hop_match.group(1))
                
                # Extract IP/hostname
                host_part = parts[1]
                if host_part.startswith('|--'):
                    host = host_part[3:].strip()
                else:
                    host = host_part.strip()
                
                # Extract statistics
                loss_pct = float(parts[2].rstrip('%'))
                sent = int(parts[3])
                
                # RTT might be in different positions depending on format
                rtt = 0.0
                for i in range(4, min(len(parts), 7)):
                    try:
                        rtt = float(parts[i])
                        break
                    except ValueError:
                        continue
                
                hop_info = {
                    'hop': hop_num,
                    'ip': host,
                    'hostname': host,
                    'rtt': rtt,
                    'loss': loss_pct,
                    'sent': sent,
                    'received': sent - int(sent * loss_pct / 100)
                }
                
                hops.append(hop_info)
                
            except (ValueError, IndexError) as e:
                if self.verbose_level >= 2:
                    print(f"DEBUG: Failed to parse MTR line: {line} - {e}", file=sys.stderr)
                continue
        
        return hops
    
    def _perform_reverse_dns(self, ip: str) -> Optional[str]:
        """Perform reverse hostname lookup for an IP address."""
        try:
            # Validate IP address first
            ipaddress.ip_address(ip)
            
            # Use getent hosts to resolve IP to hostname
            result = subprocess.run(
                ['getent', 'hosts', ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Parse getent output: "IP hostname [aliases...]"
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    hostname = parts[1]
                    return hostname
            
            return None
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, 
                ValueError, ipaddress.AddressValueError, FileNotFoundError):
            return None
    
    def execute_mtr_basic(self, source_router: str, destination_ip: str) -> List[Dict]:
        """Execute basic MTR with default options (backward compatibility)."""
        options = MTROptions(destination_ip=destination_ip)
        return self.execute_mtr_advanced(source_router, destination_ip, options)
    
    def execute_mtr_advanced(self, source_router: str, destination: str, options: MTROptions) -> List[Dict]:
        """
        Execute MTR command with advanced options on a specific router via SSH.
        
        Args:
            source_router: Hostname/IP of router to execute MTR from
            destination: Destination IP address or hostname to trace to
            options: MTR execution options
            
        Returns:
            List of dictionaries containing hop information with enhanced data
            
        Raises:
            subprocess.CalledProcessError: If SSH execution fails
            ValueError: If MTR options are invalid or output cannot be parsed
        """
        # Validate options
        self._validate_options(options)
        
        # Build MTR command
        mtr_cmd = self._build_mtr_command(source_router, destination, options)
        
        # Construct SSH command
        ssh_command = ['ssh', source_router] + mtr_cmd
        
        if self.verbose:
            print(f"Executing enhanced MTR from {source_router} to {destination}", file=sys.stderr)
            print(f"Protocol: {options.protocol.value}", file=sys.stderr)
            if options.destination_port:
                print(f"Destination port: {options.destination_port}", file=sys.stderr)
            if options.source_port:
                print(f"Source port: {options.source_port}", file=sys.stderr)
            print(f"Command: {' '.join(ssh_command)}", file=sys.stderr)
        
        try:
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=options.timeout + 10  # Add buffer to SSH timeout
            )
            
            if result.returncode != 0:
                error_msg = f"MTR execution failed on {source_router}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                raise subprocess.CalledProcessError(result.returncode, ssh_command, result.stderr)
            
            if self.verbose_level >= 2:
                print(f"DEBUG: MTR raw output:\n{result.stdout}", file=sys.stderr)
            
            # Parse MTR output
            hops = self._parse_mtr_output(result.stdout, options)
            
            # Enhance with reverse DNS if requested
            if not options.no_dns:
                for hop in hops:
                    if hop['ip'] != '???' and hop['ip'] != hop['hostname']:
                        resolved_name = self._perform_reverse_dns(hop['ip'])
                        if resolved_name:
                            hop['hostname'] = resolved_name
            
            # Filter to Linux routers if requested
            if self.linux_routers:
                filtered_hops = []
                for hop in hops:
                    if (hop['hostname'] in self.linux_routers or 
                        any(router in hop['hostname'] for router in self.linux_routers)):
                        filtered_hops.append(hop)
                    else:
                        # Keep hop but mark as non-Linux
                        hop['linux_router'] = False
                        filtered_hops.append(hop)
                hops = filtered_hops
            
            if self.verbose:
                print(f"MTR execution completed: {len(hops)} hops found", file=sys.stderr)
            
            return hops
            
        except subprocess.TimeoutExpired:
            raise ValueError(f"MTR execution timed out after {options.timeout} seconds")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"MTR execution failed: {e}")
    
    def execute_mtr_namespace(self, namespace: str, destination: str, options: MTROptions) -> List[Dict]:
        """
        Execute MTR within a network namespace.
        
        Args:
            namespace: Network namespace name
            destination: Destination IP address or hostname
            options: MTR execution options
            
        Returns:
            List of dictionaries containing hop information
        """
        # Validate options
        self._validate_options(options)
        
        # Build MTR command
        mtr_cmd = self._build_mtr_command("", destination, options)
        
        # Construct namespace command
        ns_command = ['ip', 'netns', 'exec', namespace] + mtr_cmd
        
        if self.verbose:
            print(f"Executing MTR in namespace {namespace} to {destination}", file=sys.stderr)
            print(f"Command: {' '.join(ns_command)}", file=sys.stderr)
        
        try:
            result = subprocess.run(
                ns_command,
                capture_output=True,
                text=True,
                timeout=options.timeout + 5
            )
            
            if result.returncode != 0:
                error_msg = f"MTR execution failed in namespace {namespace}"
                if result.stderr:
                    error_msg += f": {result.stderr.strip()}"
                raise subprocess.CalledProcessError(result.returncode, ns_command, result.stderr)
            
            if self.verbose_level >= 2:
                print(f"DEBUG: Namespace MTR output:\n{result.stdout}", file=sys.stderr)
            
            # Parse output
            hops = self._parse_mtr_output(result.stdout, options)
            
            if self.verbose:
                print(f"Namespace MTR completed: {len(hops)} hops found", file=sys.stderr)
            
            return hops
            
        except subprocess.TimeoutExpired:
            raise ValueError(f"MTR execution timed out in namespace {namespace}")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"MTR execution failed in namespace {namespace}: {e}")
    
    def test_connectivity(self, source_router: str, destination: str, 
                         protocol: MTRProtocol = MTRProtocol.ICMP, 
                         port: Optional[int] = None) -> Dict[str, Any]:
        """
        Test basic connectivity using MTR with minimal options.
        
        Args:
            source_router: Source router for testing
            destination: Destination IP or hostname
            protocol: Protocol to test
            port: Destination port (required for TCP/UDP)
            
        Returns:
            Dictionary with connectivity test results
        """
        options = MTROptions(
            destination_ip=destination,
            protocol=protocol,
            destination_port=port,
            packet_count=3,
            timeout=15
        )
        
        try:
            hops = self.execute_mtr_advanced(source_router, destination, options)
            
            # Analyze results
            if not hops:
                return {
                    'success': False,
                    'error': 'No hops found',
                    'reachable': False
                }
            
            last_hop = hops[-1]
            reachable = last_hop['ip'] != '???' and last_hop['loss'] < 100
            
            return {
                'success': True,
                'reachable': reachable,
                'hops': len(hops),
                'final_ip': last_hop['ip'],
                'rtt': last_hop['rtt'],
                'loss': last_hop['loss'],
                'protocol': protocol.value,
                'port': port
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'reachable': False
            }


def main():
    """Test the enhanced MTR executor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced MTR executor testing')
    parser.add_argument('source', help='Source router')
    parser.add_argument('destination', help='Destination IP/hostname')
    parser.add_argument('--protocol', choices=['icmp', 'udp', 'tcp'], 
                       default='icmp', help='Protocol to use')
    parser.add_argument('--port', type=int, help='Destination port')
    parser.add_argument('--source-port', type=int, help='Source port')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds')
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity')
    
    args = parser.parse_args()
    
    # Create executor
    executor = EnhancedMTRExecutor(verbose=args.verbose >= 1, verbose_level=args.verbose)
    
    # Configure options
    options = MTROptions(
        destination_ip=args.destination,
        protocol=MTRProtocol(args.protocol),
        destination_port=args.port,
        source_port=args.source_port,
        timeout=args.timeout
    )
    
    try:
        hops = executor.execute_mtr_advanced(args.source, args.destination, options)
        
        print(f"MTR Results: {args.source} -> {args.destination}")
        print(f"Protocol: {args.protocol}")
        if args.port:
            print(f"Port: {args.port}")
        print("-" * 50)
        
        for hop in hops:
            print(f"{hop['hop']:2d}. {hop['ip']:15s} {hop['hostname']:20s} "
                  f"{hop['rtt']:6.1f}ms {hop['loss']:5.1f}% loss")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
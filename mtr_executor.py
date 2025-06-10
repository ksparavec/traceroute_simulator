#!/usr/bin/env python3
"""
MTR Executor Module - Real Traceroute Execution and Parsing

This module handles the execution of mtr (My TraceRoute) command on Linux routers
and parses the output to extract routing information. It provides fallback
functionality when route simulation cannot determine a complete path due to
non-Linux routers in the path.

Key features:
- Executes mtr via Ansible on remote routers
- Parses mtr output to extract hop information
- Performs reverse DNS lookups for router identification
- Filters results to include only Linux routers in inventory
- Converts mtr results to simulator-compatible format

Author: Network Analysis Tool
License: MIT
"""

import subprocess
import json
import socket
import re
import sys
from typing import List, Dict, Optional, Tuple
import ipaddress


class MTRExecutor:
    """
    Executes MTR (My TraceRoute) on remote Linux routers via Ansible.
    
    This class handles the execution of real traceroute functionality when
    simulation cannot provide complete path information due to non-Linux
    routers in the network path. It uses mtr for comprehensive traceroute
    data collection and filters results based on router inventory.
    
    Attributes:
        inventory_file (str): Path to Ansible inventory file
        verbose (bool): Enable verbose output for debugging
        linux_routers (set): Set of known Linux router hostnames from inventory
    """
    
    def __init__(self, inventory_file: str = "inventory.ini", verbose: bool = False):
        """
        Initialize MTR executor with inventory information.
        
        Args:
            inventory_file: Path to Ansible inventory file containing Linux routers
            verbose: Enable verbose output for debugging operations
        """
        self.inventory_file = inventory_file
        self.verbose = verbose
        self.linux_routers = self._load_linux_routers()
    
    def _load_linux_routers(self) -> set:
        """
        Load Linux router hostnames from Ansible inventory.
        
        Parses the Ansible inventory file to extract hostnames of Linux routers
        that can be used for MTR execution. These hostnames are used later for
        filtering MTR results to include only manageable Linux infrastructure.
        
        Returns:
            Set of Linux router hostnames from inventory
            
        Raises:
            FileNotFoundError: If inventory file doesn't exist
            ValueError: If inventory file is malformed
        """
        linux_routers = set()
        
        try:
            # Try to use ansible-inventory command first (preferred method)
            result = subprocess.run(
                ['ansible-inventory', '-i', self.inventory_file, '--list'],
                capture_output=True, text=True, check=True
            )
            
            inventory_data = json.loads(result.stdout)
            
            # Extract all hosts from all groups
            for group_name, group_data in inventory_data.items():
                if isinstance(group_data, dict) and 'hosts' in group_data:
                    linux_routers.update(group_data['hosts'])
                    
            # Also check _meta.hostvars for additional hosts
            if '_meta' in inventory_data and 'hostvars' in inventory_data['_meta']:
                linux_routers.update(inventory_data['_meta']['hostvars'].keys())
                
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            # Fallback to manual parsing of INI-style inventory
            try:
                with open(self.inventory_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if line and not line.startswith('#') and not line.startswith('['):
                            # Extract hostname (first part before space or ansible vars)
                            hostname = line.split()[0].split('=')[0]
                            linux_routers.add(hostname)
            except FileNotFoundError:
                if self.verbose:
                    print(f"Warning: Inventory file {self.inventory_file} not found", file=sys.stderr)
        
        if self.verbose:
            print(f"Loaded {len(linux_routers)} Linux routers from inventory", file=sys.stderr)
            
        return linux_routers
    
    def _perform_reverse_dns(self, ip: str) -> Optional[str]:
        """
        Perform reverse DNS lookup for an IP address.
        
        Attempts to resolve IP address to hostname using reverse DNS lookup.
        This is used to identify routers by their DNS names and match them
        against the inventory of known Linux routers.
        
        Args:
            ip: IP address to perform reverse DNS lookup on
            
        Returns:
            Hostname if reverse DNS succeeds, None otherwise
        """
        try:
            # Validate IP address first
            ipaddress.ip_address(ip)
            
            # Perform reverse DNS lookup
            hostname = socket.gethostbyaddr(ip)[0]
            
            # Clean up hostname - remove domain suffix for matching
            short_hostname = hostname.split('.')[0]
            
            return short_hostname
            
        except (socket.herror, socket.gaierror, ValueError, ipaddress.AddressValueError):
            return None
    
    def _is_linux_router(self, ip: str, hostname: Optional[str] = None) -> bool:
        """
        Determine if an IP/hostname represents a Linux router in our inventory.
        
        Checks if the given IP address or hostname corresponds to a Linux router
        that we can manage via Ansible. Uses reverse DNS lookup if hostname
        is not provided, then matches against the loaded inventory.
        
        Args:
            ip: IP address to check
            hostname: Optional hostname (if not provided, reverse DNS is attempted)
            
        Returns:
            True if IP/hostname represents a known Linux router, False otherwise
        """
        if not hostname:
            hostname = self._perform_reverse_dns(ip)
        
        if not hostname:
            return False
        
        # Check against known Linux routers (case-insensitive)
        return hostname.lower() in {router.lower() for router in self.linux_routers}
    
    def execute_mtr(self, source_router: str, destination_ip: str) -> List[Dict]:
        """
        Execute MTR command on a specific router via Ansible.
        
        Runs mtr command on the specified source router to trace the path
        to the destination IP. Uses Ansible for remote execution with
        specific MTR parameters optimized for network analysis.
        
        MTR parameters used:
        - --report: Generate report format output
        - -c 1: Send only 1 packet per hop (fast execution)
        - -m 30: Maximum 30 hops (standard traceroute limit)
        
        Args:
            source_router: Name of router to execute MTR from (must be in inventory)
            destination_ip: Destination IP address to trace to
            
        Returns:
            List of dictionaries containing hop information:
            - hop: Hop number
            - ip: IP address of hop
            - hostname: Resolved hostname (if available)
            - rtt: Round trip time
            - loss: Loss percentage
            
        Raises:
            subprocess.CalledProcessError: If Ansible execution fails
            ValueError: If MTR output cannot be parsed
        """
        # Validate destination IP
        try:
            ipaddress.ip_address(destination_ip)
        except ipaddress.AddressValueError:
            raise ValueError(f"Invalid destination IP address: {destination_ip}")
        
        # Construct Ansible command to run MTR
        ansible_command = [
            'ansible', source_router,
            '-i', self.inventory_file,
            '-m', 'shell',
            '-a', f'mtr --report -c 1 -m 30 {destination_ip}'
        ]
        
        if self.verbose:
            print(f"Executing MTR from {source_router} to {destination_ip}", file=sys.stderr)
            print(f"Command: {' '.join(ansible_command)}", file=sys.stderr)
        
        try:
            result = subprocess.run(
                ansible_command,
                capture_output=True,
                text=True,
                check=True,
                timeout=60  # 60 second timeout for MTR execution
            )
            
            return self._parse_mtr_output(result.stdout)
            
        except subprocess.TimeoutExpired:
            raise ValueError("MTR execution timed out")
        except subprocess.CalledProcessError as e:
            error_msg = f"MTR execution failed on {source_router}: {e.stderr}"
            if self.verbose:
                print(error_msg, file=sys.stderr)
            raise ValueError(error_msg)
    
    def _parse_mtr_output(self, mtr_output: str) -> List[Dict]:
        """
        Parse MTR command output to extract hop information.
        
        Parses the report-format output from MTR command to extract
        structured information about each hop in the traceroute path.
        Handles various MTR output formats and error conditions.
        
        MTR report format example:
        HOST: router1                    Loss%   Snt   Last   Avg  Best  Wrst StDev
          1.|-- 192.168.1.1              0.0%     1    1.2   1.2   1.2   1.2   0.0
          2.|-- 10.0.0.1                 0.0%     1    5.4   5.4   5.4   5.4   0.0
        
        Args:
            mtr_output: Raw output from MTR command
            
        Returns:
            List of hop dictionaries with parsed information
            
        Raises:
            ValueError: If MTR output format is unrecognizable
        """
        hops = []
        
        # Split output into lines and find the data section
        lines = mtr_output.split('\n')
        in_data_section = False
        
        for line in lines:
            line = line.strip()
            
            # Skip Ansible output headers
            if 'SUCCESS' in line or 'CHANGED' in line:
                continue
            
            # Look for MTR header line
            if 'HOST:' in line and 'Loss%' in line:
                in_data_section = True
                continue
            
            # Skip empty lines
            if not line:
                continue
            
            # Parse data lines
            if in_data_section and '|--' in line:
                hop_match = re.match(r'\s*(\d+)\.\|--\s+([^\s]+)\s+([0-9.]+)%\s+\d+\s+([0-9.]+)', line)
                if hop_match:
                    hop_num = int(hop_match.group(1))
                    ip_or_hostname = hop_match.group(2)
                    loss_pct = float(hop_match.group(3))
                    rtt = float(hop_match.group(4))
                    
                    # Determine if this is an IP or hostname
                    try:
                        # Try to parse as IP address
                        ip_addr = ipaddress.ip_address(ip_or_hostname)
                        ip = str(ip_addr)
                        hostname = self._perform_reverse_dns(ip)
                    except ipaddress.AddressValueError:
                        # It's a hostname
                        hostname = ip_or_hostname
                        # Try to resolve hostname to IP
                        try:
                            ip = socket.gethostbyname(hostname)
                        except socket.gaierror:
                            ip = None
                    
                    hops.append({
                        'hop': hop_num,
                        'ip': ip,
                        'hostname': hostname,
                        'rtt': rtt,
                        'loss': loss_pct
                    })
        
        if not hops:
            raise ValueError("No valid MTR data found in output")
        
        return hops
    
    def filter_linux_hops(self, hops: List[Dict]) -> List[Dict]:
        """
        Filter MTR hops to include only Linux routers from inventory.
        
        Processes the list of MTR hops and retains only those that correspond
        to Linux routers present in the Ansible inventory. This filtering
        ensures that the final output includes only manageable infrastructure.
        
        Args:
            hops: List of hop dictionaries from MTR parsing
            
        Returns:
            Filtered list containing only Linux router hops
        """
        linux_hops = []
        
        for hop in hops:
            ip = hop.get('ip')
            hostname = hop.get('hostname')
            
            if ip and self._is_linux_router(ip, hostname):
                linux_hops.append(hop)
                if self.verbose:
                    print(f"Including hop {hop['hop']}: {ip} ({hostname})", file=sys.stderr)
            else:
                if self.verbose:
                    print(f"Filtering out hop {hop['hop']}: {ip} ({hostname}) - not a Linux router", file=sys.stderr)
        
        return linux_hops
    
    def execute_and_filter(self, source_router: str, destination_ip: str) -> List[Dict]:
        """
        Execute MTR and return filtered results with only Linux routers.
        
        This is the main method that combines MTR execution with filtering
        to provide a clean list of Linux router hops suitable for integration
        with the traceroute simulator output.
        
        Args:
            source_router: Router to execute MTR from
            destination_ip: Destination IP to trace to
            
        Returns:
            List of Linux router hops with full hop information
            
        Raises:
            ValueError: If MTR execution fails or produces no valid results
        """
        all_hops = self.execute_mtr(source_router, destination_ip)
        linux_hops = self.filter_linux_hops(all_hops)
        
        if not linux_hops and self.verbose:
            print("Warning: No Linux routers found in MTR trace", file=sys.stderr)
        
        return linux_hops
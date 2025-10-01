#!/usr/bin/env -S python3 -B -u
"""
MTR Executor Module - Real Traceroute Execution and Parsing

This module handles the execution of mtr (My TraceRoute) command on Linux routers
and parses the output to extract routing information. It provides fallback
functionality when route simulation cannot determine a complete path due to
non-Linux routers in the path.

Key features:
- Executes mtr via SSH on remote routers
- Parses mtr output to extract hop information
- Performs reverse DNS lookups for router identification
- Filters results to include only known Linux routers
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
    Executes MTR (My TraceRoute) on remote Linux routers via SSH.
    
    This class handles the execution of real traceroute functionality when
    simulation cannot provide complete path information due to non-Linux
    routers in the network path. It uses mtr for comprehensive traceroute
    data collection and filters results based on known Linux routers.
    
    Attributes:
        verbose (bool): Enable verbose output for debugging
        verbose_level (int): Verbosity level (1=basic, 2=detailed debugging)
        linux_routers (set): Set of known Linux router hostnames
    """
    
    def __init__(self, linux_routers: set = None, verbose: bool = False, verbose_level: int = 1, ssh_config: dict = None):
        """
        Initialize MTR executor with Linux router information.

        Args:
            linux_routers: Set of known Linux router hostnames (optional)
            verbose: Enable verbose output for debugging operations
            verbose_level: Verbosity level (1=basic, 2=detailed debugging)
            ssh_config: SSH configuration dictionary (optional)
        """
        self.verbose = verbose
        self.verbose_level = verbose_level
        self.linux_routers = linux_routers or set()
        self.ip_to_router_lookup = {}  # Will be set later via set_ip_lookup

        # SSH configuration (load if not provided)
        if ssh_config is None:
            try:
                from tsim.core.config_loader import get_ssh_config
                ssh_config = get_ssh_config()
            except ImportError:
                ssh_config = {}

        self.ssh_config = ssh_config or {}
        self.ssh_mode = self.ssh_config.get('ssh_mode', 'standard')
        self.ssh_user = self.ssh_config.get('ssh_user')
        self.ssh_key = self.ssh_config.get('ssh_key')
        self.ssh_options = self.ssh_config.get('ssh_options', {})
    
    def add_linux_router(self, hostname: str):
        """Add a Linux router hostname to the known routers set."""
        self.linux_routers.add(hostname)
    
    def set_ip_lookup(self, ip_lookup: dict):
        """Set the IP to router name lookup table for router identification."""
        self.ip_to_router_lookup = ip_lookup
    
    def _perform_reverse_dns(self, ip: str) -> Optional[str]:
        """
        Perform reverse hostname lookup for an IP address using getent hosts.
        
        Uses getent hosts command to resolve IP address to hostname. This approach
        queries the local system's name resolution including /etc/hosts, which may
        contain router names that are not in DNS server configuration.
        
        Args:
            ip: IP address to perform reverse lookup on
            
        Returns:
            Hostname if lookup succeeds, None otherwise
        """
        try:
            # Validate IP address first
            ipaddress.ip_address(ip)
            
            # Use getent hosts to resolve IP to hostname
            import subprocess
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
                    # Return full hostname (FQDN) to match production naming
                    return hostname
            
            return None
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, 
                ValueError, ipaddress.AddressValueError, FileNotFoundError):
            return None
    
    def _is_linux_router(self, ip: str, hostname: Optional[str] = None) -> bool:
        """
        Determine if an IP/hostname represents a Linux router in our inventory.
        
        First checks the IP lookup table for direct IP-to-router mapping,
        then falls back to hostname-based matching with reverse DNS.
        
        Args:
            ip: IP address or hostname to check
            hostname: Optional hostname (if not provided, reverse DNS is attempted)
            
        Returns:
            True if IP/hostname represents a known Linux router, False otherwise
        """
        # Debug output to see what's being passed in
        if self.verbose and self.verbose_level >= 3:
            print(f"MTR DEBUG: _is_linux_router called with ip='{ip}', hostname='{hostname}'", file=sys.stderr)
            print(f"MTR DEBUG: ip_to_router_lookup available: {bool(self.ip_to_router_lookup)}", file=sys.stderr)
            if self.ip_to_router_lookup:
                print(f"MTR DEBUG: Lookup table keys: {list(self.ip_to_router_lookup.keys())[:5]}...", file=sys.stderr)
        
        # First check direct IP lookup
        if ip and self.ip_to_router_lookup:
            router_name = self.ip_to_router_lookup.get(ip)
            if self.verbose and self.verbose_level >= 3:
                print(f"MTR DEBUG: IP lookup result: {ip} -> {router_name}", file=sys.stderr)
            if router_name:
                is_linux = router_name in self.linux_routers
                if self.verbose and self.verbose_level >= 3:
                    print(f"MTR DEBUG: Router {router_name} is_linux: {is_linux}", file=sys.stderr)
                    print(f"MTR DEBUG: Linux routers: {list(self.linux_routers)[:5]}...", file=sys.stderr)
                return is_linux
        
        # Fallback to hostname-based matching
        if not hostname:
            # Only try reverse DNS if ip is actually an IP address
            try:
                ipaddress.ip_address(ip)
                hostname = self._perform_reverse_dns(ip)
            except ipaddress.AddressValueError:
                # ip is actually a hostname
                hostname = ip
        
        if not hostname:
            return False
        
        # Extract short hostname (everything before first dot)
        short_hostname = hostname.split('.')[0].lower()
        
        # Create sets of short names from both the hostname and known routers
        # This handles cases where either could be FQDN or short names
        known_short_names = {router.split('.')[0].lower() for router in self.linux_routers}
        
        # Debug output for production troubleshooting
        if self.verbose and self.verbose_level >= 3:
            print(f"DEBUG: Checking hostname '{hostname}' -> short: '{short_hostname}'", file=sys.stderr)
            print(f"DEBUG: Known Linux routers: {list(self.linux_routers)}", file=sys.stderr)
            print(f"DEBUG: Known short names: {list(known_short_names)}", file=sys.stderr)
        
        # Check if short hostname matches any known router short name
        is_match = short_hostname in known_short_names
        
        if self.verbose and self.verbose_level >= 3:
            print(f"DEBUG: Match result for '{hostname}': {is_match}", file=sys.stderr)
        
        return is_match
    
    def execute_mtr(self, source_router: str, destination_ip: str) -> List[Dict]:
        """
        Execute MTR command on a specific router via SSH.
        
        Runs mtr command on the specified source router to trace the path
        to the destination IP. Uses SSH for direct remote execution with
        specific MTR parameters optimized for network analysis.
        
        MTR parameters used:
        - --report: Generate report format output
        - -c 1: Send only 1 packet per hop (fast execution)
        - -m 30: Maximum 30 hops (standard traceroute limit)
        
        Args:
            source_router: Hostname/IP of router to execute MTR from
            destination_ip: Destination IP address to trace to
            
        Returns:
            List of dictionaries containing hop information:
            - hop: Hop number
            - ip: IP address of hop
            - hostname: Resolved hostname (if available)
            - rtt: Round trip time
            - loss: Loss percentage
            
        Raises:
            subprocess.CalledProcessError: If SSH execution fails
            ValueError: If MTR output cannot be parsed
        """
        # Validate destination IP
        try:
            ipaddress.ip_address(destination_ip)
        except ipaddress.AddressValueError:
            raise ValueError(f"Invalid destination IP address: {destination_ip}")

        # Determine execution mode based on ansible_controller parameter
        try:
            from tsim.core.config_loader import load_traceroute_config, get_ssh_controller_config
            config = load_traceroute_config()
            ansible_controller = config.get('ansible_controller', False)
            controller_ip = config.get('controller_ip', '127.0.0.1')
        except ImportError:
            ansible_controller = False
            controller_ip = '127.0.0.1'

        if self.verbose:
            print(f"Configuration: ansible_controller={ansible_controller}, controller_ip={controller_ip}", file=sys.stderr)

        if ansible_controller:
            # We're ON the controller - execute SSH directly to routers (or locally if source_router is localhost/controller_ip)
            if source_router in ['localhost', '127.0.0.1'] or source_router == controller_ip:
                # Execute mtr locally
                # Local execution is identical for both user and standard modes
                ssh_command = ['mtr', '--report', '--no-dns', '-c', '1', '-m', '30', destination_ip]
                if self.verbose:
                    print(f"Executing mtr locally to {destination_ip}", file=sys.stderr)
            else:
                # SSH directly to router using router SSH config
                ssh_command = ['ssh']
                for option, value in self.ssh_options.items():
                    ssh_command.extend(['-o', f'{option}={value}'])

                if self.ssh_mode == 'user' and self.ssh_user and self.ssh_key:
                    ssh_command.extend(['-i', self.ssh_key])
                    ssh_command.extend(['-l', self.ssh_user])
                    ssh_command.extend([source_router, destination_ip])
                    if self.verbose:
                        print(f"Executing trace in user mode from {source_router} to {destination_ip}", file=sys.stderr)
                        print(f"SSH user: {self.ssh_user}, Key: {self.ssh_key}", file=sys.stderr)
                else:
                    ssh_command.extend([source_router, f'mtr --report --no-dns -c 1 -m 30 {destination_ip}'])
                    if self.verbose:
                        print(f"Executing mtr tool from {source_router} to {destination_ip}", file=sys.stderr)
        else:
            # We're NOT on the controller - need to connect via controller_ip using controller SSH config
            if source_router == controller_ip:
                # Target is the controller itself - use controller SSH config
                try:
                    controller_ssh_config = get_ssh_controller_config()
                    controller_ssh_mode = controller_ssh_config.get('ssh_mode', 'standard')
                    controller_ssh_user = controller_ssh_config.get('ssh_user')
                    controller_ssh_key = controller_ssh_config.get('ssh_key')
                    controller_ssh_options = controller_ssh_config.get('ssh_options', {})
                except ImportError:
                    controller_ssh_mode = 'standard'
                    controller_ssh_user = None
                    controller_ssh_key = None
                    controller_ssh_options = {'BatchMode': 'yes', 'ConnectTimeout': '10'}

                ssh_command = ['ssh']
                for option, value in controller_ssh_options.items():
                    ssh_command.extend(['-o', f'{option}={value}'])

                if controller_ssh_mode == 'user' and controller_ssh_user and controller_ssh_key:
                    ssh_command.extend(['-i', controller_ssh_key])
                    ssh_command.extend(['-l', controller_ssh_user])
                    ssh_command.extend([source_router, destination_ip])
                    if self.verbose:
                        print(f"Executing trace via controller in user mode from {source_router} to {destination_ip}", file=sys.stderr)
                        print(f"Controller SSH user: {controller_ssh_user}, Key: {controller_ssh_key}", file=sys.stderr)
                else:
                    ssh_command.extend([source_router, f'mtr --report --no-dns -c 1 -m 30 {destination_ip}'])
                    if self.verbose:
                        print(f"Executing mtr via controller from {source_router} to {destination_ip}", file=sys.stderr)
            else:
                # Target is a router - use nested SSH (controller -> router)
                try:
                    controller_ssh_config = get_ssh_controller_config()
                    controller_ssh_mode = controller_ssh_config.get('ssh_mode', 'standard')
                    controller_ssh_user = controller_ssh_config.get('ssh_user')
                    controller_ssh_key = controller_ssh_config.get('ssh_key')
                    controller_ssh_options = controller_ssh_config.get('ssh_options', {})
                except ImportError:
                    controller_ssh_mode = 'standard'
                    controller_ssh_user = None
                    controller_ssh_key = None
                    controller_ssh_options = {'BatchMode': 'yes', 'ConnectTimeout': '10'}

                # Build outer SSH command to controller
                ssh_command = ['ssh']
                for option, value in controller_ssh_options.items():
                    ssh_command.extend(['-o', f'{option}={value}'])

                if controller_ssh_mode == 'user' and controller_ssh_user and controller_ssh_key:
                    ssh_command.extend(['-i', controller_ssh_key])
                    ssh_command.extend(['-l', controller_ssh_user])

                # Build inner SSH command with router options
                inner_ssh_opts = []
                for option, value in self.ssh_options.items():
                    inner_ssh_opts.extend(['-o', f'{option}={value}'])

                if self.ssh_mode == 'user' and self.ssh_user and self.ssh_key:
                    # User mode: nested SSH with trace command
                    inner_ssh_opts.extend(['-i', self.ssh_key, '-l', self.ssh_user])
                    inner_cmd = f"ssh {' '.join(inner_ssh_opts)} {source_router} {destination_ip}"
                    ssh_command.extend([controller_ip, inner_cmd])
                    if self.verbose:
                        print(f"Executing nested trace via controller from {source_router} to {destination_ip}", file=sys.stderr)
                        print(f"Controller SSH user: {controller_ssh_user}, Router SSH user: {self.ssh_user}", file=sys.stderr)
                else:
                    # Standard mode: nested SSH with mtr command
                    inner_cmd = f"ssh {' '.join(inner_ssh_opts)} {source_router} 'mtr --report --no-dns -c 1 -m 30 {destination_ip}'"
                    ssh_command.extend([controller_ip, inner_cmd])
                    if self.verbose:
                        print(f"Executing nested mtr via controller from {source_router} to {destination_ip}", file=sys.stderr)

        if self.verbose:
            print(f"Command: {' '.join(ssh_command)}", file=sys.stderr)
        
        try:
            result = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                check=True,
                timeout=60  # 60 second timeout for MTR execution
            )
            
            # Show command output in detailed debug mode
            if self.verbose_level >= 2:
                mode_str = "USER MODE" if self.ssh_mode == 'user' else "MTR"
                print(f"=== {mode_str} COMMAND OUTPUT ===", file=sys.stderr)
                print(f"STDOUT:\n{result.stdout}", file=sys.stderr)
                if result.stderr:
                    print(f"STDERR:\n{result.stderr}", file=sys.stderr)
                print(f"=== END {mode_str} OUTPUT ===", file=sys.stderr)

            # Parse output based on mode
            if self.ssh_mode == 'user' and self.ssh_user:
                return self._parse_user_mode_output(result.stdout)
            else:
                return self._parse_mtr_output(result.stdout)
            
        except subprocess.TimeoutExpired:
            raise ValueError("mtr tool execution timed out")
        except subprocess.CalledProcessError as e:
            error_msg = f"mtr tool execution failed on {source_router}: {e.stderr}"
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
            mtr_output: Raw output from MTR command via SSH
            
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
            
            # Skip empty lines
            if not line:
                continue
            
            # Look for MTR header line
            if 'HOST:' in line and 'Loss%' in line:
                in_data_section = True
                continue
            
            # Parse data lines
            if in_data_section and '|--' in line:
                hop_match = re.match(
                    r'\s*(\d+)\.\|--\s+([^\s]+)\s+([0-9.]+)%\s+\d+\s+([0-9.]+)', 
                    line
                )
                if hop_match:
                    hop_num = int(hop_match.group(1))
                    ip_or_hostname = hop_match.group(2)
                    loss_pct = float(hop_match.group(3))
                    rtt = float(hop_match.group(4))
                    
                    # Determine if this is an IP or hostname
                    ip = None
                    hostname = None
                    
                    try:
                        # Try to parse as IP address
                        ip_addr = ipaddress.ip_address(ip_or_hostname)
                        ip = str(ip_addr)
                        hostname = self._perform_reverse_dns(ip)
                    except (ipaddress.AddressValueError, ValueError):
                        # It's a hostname
                        hostname = ip_or_hostname
                        # Try to resolve hostname to IP using getent hosts
                        try:
                            import subprocess
                            result = subprocess.run(
                                ['getent', 'hosts', hostname],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                # Parse getent output: "IP hostname [aliases...]"
                                parts = result.stdout.strip().split()
                                if len(parts) >= 1:
                                    ip = parts[0]
                                else:
                                    ip = ip_or_hostname  # Use hostname as IP placeholder
                            else:
                                ip = ip_or_hostname  # Use hostname as IP placeholder
                        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, 
                                FileNotFoundError):
                            # Can't resolve hostname, but that's okay
                            ip = ip_or_hostname  # Use hostname as IP placeholder
                    
                    hops.append({
                        'hop': hop_num,
                        'ip': ip,
                        'hostname': hostname,
                        'rtt': rtt,
                        'loss': loss_pct
                    })
        
        if not hops:
            raise ValueError("No valid mtr tool data found in output")
        
        return hops

    def _parse_user_mode_output(self, output: str) -> List[Dict]:
        """
        Parse user mode SSH output to extract hop information.

        User mode format is CSV with comment header:
        - First line: comment starting with #
        - Data lines: hop_number,ip_address,rtt_ms,status_code

        Args:
            output: Raw output from SSH user mode command

        Returns:
            List of hop dictionaries with parsed information

        Raises:
            ValueError: If output format is unrecognizable
        """
        hops = []
        lines = output.strip().split('\n')

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Skip comment lines starting with #
            if line.startswith('#'):
                if self.verbose_level >= 2:
                    print(f"Skipping comment line: {line}", file=sys.stderr)
                continue

            # Parse CSV format: hop_number,ip_address,rtt_ms,status_code
            parts = line.split(',')
            if len(parts) >= 4:
                try:
                    hop_num = int(parts[0])
                    ip = parts[1].strip()
                    rtt = float(parts[2])
                    status = int(parts[3])

                    # Validate IP address
                    try:
                        ipaddress.ip_address(ip)
                    except ipaddress.AddressValueError:
                        if self.verbose:
                            print(f"Warning: Invalid IP in user mode output: {ip}", file=sys.stderr)
                        continue

                    # Perform reverse DNS lookup for hostname
                    hostname = self._perform_reverse_dns(ip)

                    # Convert status code to loss percentage (0=success, other=100% loss)
                    loss_pct = 0.0 if status == 0 else 100.0

                    hops.append({
                        'hop': hop_num,
                        'ip': ip,
                        'hostname': hostname,
                        'rtt': rtt,
                        'loss': loss_pct
                    })

                    if self.verbose_level >= 2:
                        print(f"Parsed hop {hop_num}: {ip} ({hostname}), RTT={rtt}ms, Loss={loss_pct}%", file=sys.stderr)

                except (ValueError, IndexError) as e:
                    if self.verbose:
                        print(f"Warning: Failed to parse line '{line}': {e}", file=sys.stderr)
                    continue
            else:
                if self.verbose_level >= 2:
                    print(f"Skipping malformed line (expected 4+ fields): {line}", file=sys.stderr)

        if not hops:
            raise ValueError("No valid hop data found in user mode output")

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
                if self.verbose and self.verbose_level >= 3:
                    print(f"Including hop {hop['hop']}: {ip} ({hostname})", file=sys.stderr)
            else:
                if self.verbose and self.verbose_level >= 3:
                    print(f"Filtering out hop {hop['hop']}: {ip} ({hostname}) - "
                          f"not a Linux router", file=sys.stderr)
        
        return linux_hops
    
    def execute_and_filter(
        self, source_router: str, destination_ip: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Execute MTR via SSH and return both all hops and filtered Linux router hops.
        
        This is the main method that combines MTR execution with filtering
        to provide both complete hop information and filtered Linux router hops
        for comprehensive traceroute output formatting.
        
        Args:
            source_router: Router hostname/IP to execute MTR from via SSH
            destination_ip: Destination IP to trace to
            
        Returns:
            Tuple of (all_hops, linux_hops) where:
            - all_hops: Complete list of MTR hops (unfiltered)
            - linux_hops: Filtered list containing only Linux routers
            
        Raises:
            ValueError: If SSH/MTR execution fails or produces no valid results
        """
        all_hops = self.execute_mtr(source_router, destination_ip)
        linux_hops = self.filter_linux_hops(all_hops)
        
        if self.verbose and self.verbose_level >= 3:
            print(f"MTR execute_and_filter result: all_hops={len(all_hops)}, linux_hops={len(linux_hops)}", file=sys.stderr)
        
        if not linux_hops and self.verbose:
            print("Warning: No Linux routers found in mtr tool trace", file=sys.stderr)
        
        return all_hops, linux_hops
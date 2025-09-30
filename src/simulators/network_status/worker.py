#!/usr/bin/env -S python3 -B -u
"""
Worker for executing namespace queries in parallel.

Handles individual namespace command execution with timeout
and error handling.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Dict, List, Optional, Any, Tuple

from tsim.simulators.network_status.exceptions import CollectionError, TimeoutError


logger = logging.getLogger(__name__)


class NamespaceQueryWorker:
    """
    Worker for executing commands in network namespaces.
    
    Designed to be used by thread pool executor for parallel
    data collection from multiple namespaces.
    """
    
    def __init__(self, timeout: int = 5, use_json: bool = True):
        """
        Initialize namespace query worker.
        
        Args:
            timeout: Command timeout in seconds
            use_json: Use JSON output where available
        """
        self.timeout = timeout
        self.use_json = use_json
        self.needs_sudo = os.geteuid() != 0
        self.timeout_callback = None  # Optional callback for timeout tracking
    
    async def execute_command(self, command: str, namespace: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Execute a command optionally in a namespace asynchronously.
        
        Args:
            command: Command to execute
            namespace: Optional namespace name
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        # Build full command
        if namespace:
            if self.needs_sudo:
                full_command = f"sudo ip netns exec {namespace} {command}"
            else:
                full_command = f"ip netns exec {namespace} {command}"
        else:
            if self.needs_sudo and (command.startswith("ip netns") or namespace):
                full_command = f"sudo {command}"
            else:
                full_command = command
        
        logger.debug(f"Executing: {full_command}")
        
        proc = None
        try:
            # Use asyncio subprocess for true parallel execution
            # Start new process group to enable proper cleanup
            proc = await asyncio.create_subprocess_shell(
                full_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, 'setsid') else None
            )
            
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            
            return proc.returncode, stdout, stderr
            
        except asyncio.TimeoutError:
            # Log the timeout with full command details for summary
            timeout_msg = f"TIMEOUT after {self.timeout}s: {full_command}"
            if namespace:
                timeout_msg += f" (namespace: {namespace})"
            logger.warning(timeout_msg)
            
            # Record timeout details for summary if callback is set
            if self.timeout_callback and namespace:
                self.timeout_callback(command, namespace, self.timeout)
            
            # Terminate the process and its children more aggressively
            if proc:
                try:
                    # Try to terminate the process group first
                    if hasattr(os, 'killpg') and proc.pid:
                        try:
                            os.killpg(os.getpgid(proc.pid), 15)  # SIGTERM
                            # Give it a moment to terminate gracefully
                            try:
                                await asyncio.wait_for(proc.wait(), timeout=2.0)
                            except asyncio.TimeoutError:
                                # Force kill if it doesn't terminate
                                os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL
                        except (ProcessLookupError, OSError):
                            # Process group doesn't exist or already terminated
                            pass
                    
                    # Fallback: kill the main process directly
                    if proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                        
                except Exception as kill_error:
                    logger.debug(f"Error during process cleanup: {kill_error}")
            
            raise TimeoutError(f"Command timeout after {self.timeout}s: {command}")
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise CollectionError(f"Failed to execute command: {e}")
    
    async def query_interfaces(self, namespace: str) -> Dict[str, Any]:
        """
        Query interface information for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary with interface data
        """
        try:
            if self.use_json:
                # Try JSON output first
                returncode, stdout, stderr = await self.execute_command("ip -j addr show", namespace)
                
                if returncode == 0 and stdout:
                    try:
                        interfaces = json.loads(stdout)
                        return self._parse_json_interfaces(interfaces)
                    except json.JSONDecodeError:
                        logger.debug(f"Failed to parse JSON output for {namespace}, falling back to text")
            
            # Fallback to text parsing
            returncode, stdout, stderr = await self.execute_command("ip addr show", namespace)
            
            if returncode != 0:
                return {'error': f"Command failed: {stderr}"}
            
            return self._parse_text_interfaces(stdout)
            
        except TimeoutError:
            return {'error': 'Query timeout'}
        except Exception as e:
            logger.error(f"Failed to query interfaces for {namespace}: {e}")
            return {'error': str(e)}
    
    async def query_routes(self, namespace: str) -> Dict[str, Any]:
        """
        Query routing tables for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary with routing data
        """
        try:
            routes = {}
            
            # First discover routing tables from policy rules
            tables = await self._discover_routing_tables(namespace)
            
            for table_id, table_name in tables:
                if self.use_json:
                    if table_name == 'main':
                        cmd = "ip -j route show"
                    else:
                        cmd = f"ip -j route show table {table_id}"
                    
                    returncode, stdout, stderr = await self.execute_command(cmd, namespace)
                    
                    if returncode == 0 and stdout:
                        try:
                            route_data = json.loads(stdout)
                            routes[table_name] = route_data
                            continue
                        except json.JSONDecodeError:
                            pass
                
                # Fallback to text parsing
                if table_name == 'main':
                    cmd = "ip route show"
                else:
                    cmd = f"ip route show table {table_id}"
                
                returncode, stdout, stderr = await self.execute_command(cmd, namespace)
                
                if returncode == 0:
                    routes[table_name] = self._parse_text_routes(stdout)
                else:
                    routes[table_name] = {'error': f"Failed to get routes: {stderr}"}
            
            return routes
            
        except TimeoutError:
            return {'error': 'Query timeout'}
        except Exception as e:
            logger.error(f"Failed to query routes for {namespace}: {e}")
            return {'error': str(e)}
    
    async def query_rules(self, namespace: str) -> List[Dict[str, Any]]:
        """
        Query policy routing rules for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            List of rule dictionaries
        """
        try:
            if self.use_json:
                returncode, stdout, stderr = await self.execute_command("ip -j rule show", namespace)
                
                if returncode == 0 and stdout:
                    try:
                        return json.loads(stdout)
                    except json.JSONDecodeError:
                        pass
            
            # Fallback to text parsing
            returncode, stdout, stderr = await self.execute_command("ip rule show", namespace)
            
            if returncode != 0:
                return [{'error': f"Command failed: {stderr}"}]
            
            return self._parse_text_rules(stdout)
            
        except TimeoutError:
            return [{'error': 'Query timeout'}]
        except Exception as e:
            logger.error(f"Failed to query rules for {namespace}: {e}")
            return [{'error': str(e)}]
    
    async def query_iptables(self, namespace: str) -> Dict[str, Any]:
        """
        Query iptables configuration for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary with iptables data for all tables
        """
        try:
            iptables_data = {}
            tables = ['filter', 'nat', 'mangle', 'raw']
            
            for table in tables:
                # Use iptables-save for structured output with counters
                cmd = f"iptables-save -t {table} -c"
                returncode, stdout, stderr = await self.execute_command(cmd, namespace)
                
                if returncode == 0:
                    iptables_data[table] = self._parse_iptables_save(stdout)
                else:
                    iptables_data[table] = {'error': f"Failed to get {table} table"}
            
            return iptables_data
            
        except TimeoutError:
            return {'error': 'Query timeout'}
        except Exception as e:
            logger.error(f"Failed to query iptables for {namespace}: {e}")
            return {'error': str(e)}
    
    async def query_ipsets(self, namespace: str) -> Dict[str, Any]:
        """
        Query ipset configuration for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary with ipset data
        """
        try:
            # Use single ipset save command to get all ipsets at once
            returncode, stdout, stderr = await self.execute_command("ipset save", namespace)
            
            if returncode != 0:
                # No ipsets or command failed
                return {}
            
            return self._parse_ipset_save(stdout)
            
        except TimeoutError:
            return {'error': 'Query timeout'}
        except Exception as e:
            logger.error(f"Failed to query ipsets for {namespace}: {e}")
            return {'error': str(e)}
    
    async def query_all(self, namespace: str) -> Dict[str, Any]:
        """
        Query all information for a namespace.
        
        Args:
            namespace: Namespace name
            
        Returns:
            Dictionary with all namespace data
        """
        return {
            'namespace': namespace,
            'interfaces': await self.query_interfaces(namespace),
            'routes': await self.query_routes(namespace),
            'rules': await self.query_rules(namespace),
            'iptables': await self.query_iptables(namespace),
            'ipsets': await self.query_ipsets(namespace)
        }
    
    # Helper methods for parsing text output
    
    async def _discover_routing_tables(self, namespace: str) -> List[Tuple[str, str]]:
        """Discover routing tables from policy rules."""
        discovered_tables = []
        seen_tables = set()
        
        returncode, stdout, stderr = await self.execute_command("ip rule show", namespace)
        
        if returncode != 0:
            # Default to main table only
            return [('main', 'main')]
        
        for line in stdout.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Look for table references
            table_match = re.search(r'(?:lookup|table)\s+(\w+)', line)
            if table_match:
                table_ref = table_match.group(1)
                
                # Skip system tables
                if table_ref in ['local', 'default']:
                    continue
                
                if table_ref not in seen_tables:
                    if table_ref == 'main':
                        discovered_tables.append(('main', 'main'))
                    elif table_ref.isdigit():
                        discovered_tables.append((table_ref, f"table_{table_ref}"))
                    else:
                        discovered_tables.append((table_ref, table_ref))
                    seen_tables.add(table_ref)
        
        # Ensure main table is included
        if 'main' not in seen_tables:
            discovered_tables.insert(0, ('main', 'main'))
        
        return discovered_tables
    
    def _parse_json_interfaces(self, interfaces: List[Dict]) -> Dict[str, Any]:
        """Parse JSON interface data."""
        result = {}
        for iface in interfaces:
            name = iface.get('ifname', 'unknown')
            addresses = []
            for addr_info in iface.get('addr_info', []):
                if addr_info.get('family') == 'inet':
                    ip = addr_info.get('local', '')
                    prefix = addr_info.get('prefixlen', 32)
                    addresses.append(f"{ip}/{prefix}")
            result[name] = {
                'addresses': addresses,
                'state': iface.get('operstate', 'unknown'),
                'mtu': iface.get('mtu', 0)
            }
        return result
    
    def _parse_text_interfaces(self, output: str) -> Dict[str, Any]:
        """Parse text interface output."""
        interfaces = {}
        current_iface = None
        
        for line in output.split('\n'):
            # Interface line
            if_match = re.match(r'^(\d+):\s+([^@:]+)(@[^:]*)?:', line)
            if if_match:
                current_iface = if_match.group(2)
                interfaces[current_iface] = {'addresses': [], 'state': 'unknown', 'mtu': 0}
            
            # IP address line
            elif current_iface and 'inet ' in line:
                ip_match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', line)
                if ip_match:
                    interfaces[current_iface]['addresses'].append(ip_match.group(1))
            
            # State and MTU
            elif current_iface and 'state ' in line:
                state_match = re.search(r'state (\w+)', line)
                if state_match:
                    interfaces[current_iface]['state'] = state_match.group(1)
                mtu_match = re.search(r'mtu (\d+)', line)
                if mtu_match:
                    interfaces[current_iface]['mtu'] = int(mtu_match.group(1))
        
        return interfaces
    
    def _parse_text_routes(self, output: str) -> List[Dict[str, Any]]:
        """Parse text route output."""
        routes = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            route = {}
            parts = line.split()
            
            # Parse destination
            if parts[0] == 'default':
                route['dst'] = 'default'
                i = 1
            else:
                route['dst'] = parts[0]
                i = 1
            
            # Parse remaining parts
            while i < len(parts):
                if parts[i] == 'via' and i + 1 < len(parts):
                    route['gateway'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'dev' and i + 1 < len(parts):
                    route['dev'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'proto' and i + 1 < len(parts):
                    route['protocol'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'scope' and i + 1 < len(parts):
                    route['scope'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'src' and i + 1 < len(parts):
                    route['prefsrc'] = parts[i + 1]
                    i += 2
                elif parts[i] == 'metric' and i + 1 < len(parts):
                    route['metric'] = int(parts[i + 1])
                    i += 2
                else:
                    i += 1
            
            routes.append(route)
        
        return routes
    
    def _parse_text_rules(self, output: str) -> List[Dict[str, Any]]:
        """Parse text policy rules output."""
        rules = []
        for line in output.split('\n'):
            if not line.strip():
                continue
            
            rule = {}
            priority_match = re.match(r'^(\d+):\s+(.+)$', line)
            if priority_match:
                rule['priority'] = int(priority_match.group(1))
                rule_text = priority_match.group(2)
                
                # Parse rule components
                if from_match := re.search(r'from (\S+)', rule_text):
                    rule['src'] = from_match.group(1)
                if to_match := re.search(r'to (\S+)', rule_text):
                    rule['dst'] = to_match.group(1)
                if lookup_match := re.search(r'lookup (\S+)', rule_text):
                    rule['table'] = lookup_match.group(1)
                if iif_match := re.search(r'iif (\S+)', rule_text):
                    rule['iifname'] = iif_match.group(1)
                if oif_match := re.search(r'oif (\S+)', rule_text):
                    rule['oifname'] = oif_match.group(1)
                
                rules.append(rule)
        
        return rules
    
    def _parse_iptables_save(self, output: str) -> Dict[str, Any]:
        """Parse iptables-save output."""
        table_data = {'chains': {}, 'custom_chains': []}
        
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('*') or line == 'COMMIT':
                continue
            
            # Chain definition
            if line.startswith(':'):
                chain_match = re.match(r':(\S+)\s+(\S+)(?:\s+\[(\d+):(\d+)\])?', line)
                if chain_match:
                    chain_name = chain_match.group(1)
                    chain_policy = chain_match.group(2)
                    packets = int(chain_match.group(3)) if chain_match.group(3) else 0
                    bytes_count = int(chain_match.group(4)) if chain_match.group(4) else 0
                    
                    table_data['chains'][chain_name] = {
                        'policy': chain_policy if chain_policy != '-' else None,
                        'packets': packets,
                        'bytes': bytes_count,
                        'rules': []
                    }
                    
                    if chain_policy == '-':
                        table_data['custom_chains'].append(chain_name)
            
            # Rule
            elif line.startswith('[') or line.startswith('-A '):
                # Parse rule (simplified for brevity)
                if '-A ' in line:
                    chain_match = re.search(r'-A (\S+)', line)
                    if chain_match:
                        chain_name = chain_match.group(1)
                        if chain_name in table_data['chains']:
                            table_data['chains'][chain_name]['rules'].append({'raw': line})
        
        return table_data
    
    def _parse_ipset_save(self, output: str) -> Dict[str, Any]:
        """Parse ipset save output and return same structure as _parse_ipset_list."""
        ipsets = {}
        current_ipset = None
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('create '):
                # Parse create line: create NAME type options...
                parts = line.split()
                ipset_name = parts[1]
                ipset_type = parts[2]
                
                # Parse options
                header = {}
                i = 3
                while i < len(parts):
                    if i + 1 < len(parts) and not parts[i+1].startswith('-'):
                        header[parts[i]] = parts[i+1]
                        i += 2
                    else:
                        header[parts[i]] = True
                        i += 1
                
                current_ipset = ipset_name
                ipsets[ipset_name] = {
                    'type': ipset_type,
                    'header': header,
                    'members': []
                }
                
            elif line.startswith('add ') and current_ipset:
                # Parse add line: add NAME member
                parts = line.split(' ', 2)
                if len(parts) >= 3:
                    member = parts[2]
                    ipsets[current_ipset]['members'].append(member)
        
        return ipsets
    
    def _parse_ipset_list(self, output: str) -> Dict[str, Any]:
        """Parse ipset list output."""
        ipset_info = {'type': None, 'header': {}, 'members': []}
        in_members = False
        
        for line in output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line == 'Members:':
                in_members = True
                continue
            
            if not in_members:
                if line.startswith('Type:'):
                    ipset_info['type'] = line.split(':', 1)[1].strip()
                elif ':' in line:
                    key, value = line.split(':', 1)
                    ipset_info['header'][key.strip()] = value.strip()
            else:
                ipset_info['members'].append(line)
        
        return ipset_info
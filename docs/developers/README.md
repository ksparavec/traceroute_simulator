# Python Developer Guide

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Organization](#code-organization)
3. [Core Components](#core-components)
4. [tsimsh Command Implementation](#tsimsh-command-implementation)
5. [Firewall Analysis Engine](#firewall-analysis-engine)
6. [Network Namespace Management](#network-namespace-management)
7. [Data Models and Storage](#data-models-and-storage)
8. [Testing Framework](#testing-framework)
9. [Extension Points](#extension-points)
10. [Development Workflow](#development-workflow)

## Architecture Overview

### System Layers

```python
"""
Layer Architecture:

┌─────────────────────────────────────────────────────────┐
│                   Presentation Layer                      │
│  • tsimsh (cmd2)    • Web CGI      • CLI Scripts        │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                      │
│  • Command Handlers  • Request Processing               │
│  • Response Formatting • Error Handling                 │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│                     Business Logic                        │
│  • TracerouteSimulator  • IptablesForwardAnalyzer      │
│  • NetworkNamespaceManager • ServiceManager             │
│  • PacketTracer • MTRExecutor • ReversePathTracer      │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│                      Data Access                          │
│  • FactsLoader    • RawFactsParser    • HostRegistry   │
│  • ConfigManager  • SharedMemoryManager                 │
└─────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────┐
│                     Infrastructure                        │
│  • Linux Namespaces  • iptables/netfilter              │
│  • iproute2         • Process Management                │
└─────────────────────────────────────────────────────────┘
"""
```

### Design Patterns

The codebase implements several design patterns:

```python
# Singleton Pattern - Configuration Manager
class ConfigManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

# Factory Pattern - Command Creation
class CommandFactory:
    @staticmethod
    def create_command(cmd_type: str) -> BaseCommand:
        if cmd_type == "trace":
            return TraceCommand()
        elif cmd_type == "network":
            return NetworkCommand()
        # ...

# Strategy Pattern - Output Formatting
class OutputFormatter(ABC):
    @abstractmethod
    def format(self, data: dict) -> str:
        pass

class JSONFormatter(OutputFormatter):
    def format(self, data: dict) -> str:
        return json.dumps(data, indent=2)

class TextFormatter(OutputFormatter):
    def format(self, data: dict) -> str:
        # Format as human-readable text
        pass
```

## Code Organization

### Directory Structure

```
src/
├── core/                      # Core business logic
│   ├── __init__.py
│   ├── traceroute_simulator.py    # Main simulator class
│   ├── models.py                   # Data models
│   ├── exceptions.py               # Custom exceptions
│   ├── packet_tracer.py           # Packet tracing logic
│   ├── reverse_path_tracer.py     # Reverse path analysis
│   ├── raw_facts_parser.py        # Raw facts processing
│   ├── rule_database.py           # Iptables rule management
│   └── tsim_shm_manager.py        # Shared memory management
│
├── shell/                     # Interactive shell (tsimsh)
│   ├── __init__.py
│   ├── tsim_shell.py              # Main shell class
│   ├── commands/                  # Command implementations
│   │   ├── base.py               # Base command class
│   │   ├── trace.py              # Trace commands
│   │   ├── network.py            # Network management
│   │   ├── service.py            # Service management
│   │   ├── host.py               # Host management
│   │   └── facts.py              # Facts management
│   ├── completers/               # Tab completion
│   │   └── dynamic.py            # Dynamic completers
│   └── utils/                    # Shell utilities
│       ├── variable_manager.py   # Variable handling
│       ├── script_processor.py   # Script execution
│       └── history_handler.py    # Command history
│
├── analyzers/                 # Analysis engines
│   ├── __init__.py
│   ├── iptables_forward_analyzer.py  # Firewall analysis
│   └── iptables_log_processor.py     # Log analysis
│
├── simulators/                # Network simulation
│   ├── __init__.py
│   ├── network_namespace_manager.py  # Namespace management
│   ├── network_namespace_setup.py    # Setup logic
│   ├── network_namespace_status.py   # Status monitoring
│   ├── service_manager.py           # Service management
│   └── service_tester.py            # Service testing
│
├── executors/                 # External command execution
│   ├── __init__.py
│   ├── mtr_executor.py              # MTR integration
│   └── enhanced_mtr_executor.py     # Enhanced MTR
│
├── utils/                     # Utility functions
│   ├── __init__.py
│   ├── host_cleanup.py             # Host cleanup
│   ├── verify_network_setup.py     # Setup verification
│   └── update_tsim_facts.py        # Facts updates
│
└── scripts/                   # Standalone scripts
    ├── visualize_reachability.py   # Network visualization
    └── format_reachability_output.py # Output formatting
```

### Module Dependencies

```python
# Core dependencies graph
"""
traceroute_simulator.py
    ├── models.py
    ├── raw_facts_parser.py
    │   └── raw_facts_block_loader.py
    ├── packet_tracer.py
    │   └── iptables_forward_analyzer.py
    └── mtr_executor.py
        └── subprocess

tsim_shell.py
    ├── commands/*.py
    │   └── traceroute_simulator.py
    ├── completers/dynamic.py
    └── utils/*.py

network_namespace_manager.py
    ├── models.py
    ├── subprocess
    └── tsim_shm_manager.py
"""
```

## Core Components

### TracerouteSimulator Class

Location: `src/core/traceroute_simulator.py`

```python
class TracerouteSimulator:
    """Main simulator class that orchestrates path tracing."""
    
    def __init__(self, facts_dir: str = None):
        """
        Initialize simulator with router facts.
        
        Args:
            facts_dir: Directory containing router JSON facts
        """
        self.facts_dir = facts_dir or os.environ.get('TRACEROUTE_SIMULATOR_FACTS')
        self.routers = self._load_routers()
        self.raw_facts_parser = RawFactsParser()
        
    def simulate_traceroute(self, source_ip: str, dest_ip: str, 
                           source_port: int = None, dest_port: int = None,
                           protocol: str = 'icmp') -> List[dict]:
        """
        Simulate traceroute from source to destination.
        
        Returns:
            List of hop dictionaries with router and interface info
        """
        # 1. Find source router
        source_router = self._find_router_by_ip(source_ip)
        
        # 2. Build path iteratively
        path = []
        current_router = source_router
        
        while current_router:
            # 3. Find next hop
            next_hop_info = self._find_next_hop(current_router, dest_ip)
            
            # 4. Check if destination reached
            if self._is_destination(current_router, dest_ip):
                break
                
            # 5. Move to next router
            current_router = self._find_router_by_ip(next_hop_info['gateway'])
            path.append(next_hop_info)
            
        return path
    
    def _find_next_hop(self, router: dict, dest_ip: str) -> dict:
        """
        Find next hop using Linux routing logic.
        
        Implements:
        1. Policy routing (ip rules)
        2. Multiple routing tables
        3. Longest prefix match
        4. Default routes
        """
        # Implementation details...
```

### Key Methods to Understand

```python
# Route selection algorithm
def _find_best_route(self, routes: List[dict], dest_ip: str) -> dict:
    """
    Implements Linux route selection:
    1. Longest prefix match
    2. Lowest metric
    3. Table priority
    """
    
# Router discovery
def _find_router_by_ip(self, ip: str) -> dict:
    """
    Find router that owns an IP address.
    Checks all interfaces across all routers.
    """
    
# Reachability validation
def _validate_ip_reachability(self, ip: str) -> bool:
    """
    Check if IP is reachable through known routers.
    Handles:
    - Direct connections
    - Routed networks
    - Internet access via gateways
    """
```

## tsimsh Command Implementation

### Command Structure

Location: `src/shell/commands/`

```python
# Base command class - src/shell/commands/base.py
class BaseCommand(cmd2.CommandSet):
    """Base class for all tsimsh commands."""
    
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.simulator = shell.simulator
        
    def print_error(self, message: str):
        """Print error message in red."""
        self.shell.poutput(self.shell.colorize(f"Error: {message}", "red"))
        
    def print_success(self, message: str):
        """Print success message in green."""
        self.shell.poutput(self.shell.colorize(message, "green"))
```

### Implementing a New Command

Example: Adding a "diagnostic" command

```python
# src/shell/commands/diagnostic.py
from .base import BaseCommand
import cmd2
from cmd2 import with_argparser
import argparse

class DiagnosticCommand(BaseCommand):
    """Diagnostic commands for troubleshooting."""
    
    # Create argument parser
    diag_parser = argparse.ArgumentParser()
    diag_parser.add_argument('--router', required=True,
                            help='Router to diagnose')
    diag_parser.add_argument('--check', choices=['routes', 'firewall', 'all'],
                            default='all', help='What to check')
    
    @with_argparser(diag_parser)
    def do_diagnostic(self, args):
        """Run diagnostic checks on a router."""
        
        # Find router in facts
        router = self._find_router(args.router)
        if not router:
            self.print_error(f"Router {args.router} not found")
            return
            
        # Run diagnostics
        if args.check in ['routes', 'all']:
            self._check_routes(router)
            
        if args.check in ['firewall', 'all']:
            self._check_firewall(router)
            
    def _check_routes(self, router: dict):
        """Check routing configuration."""
        # Implementation
        pass
        
    def _check_firewall(self, router: dict):
        """Check firewall rules."""
        # Implementation
        pass

# Register in tsim_shell.py
from .commands.diagnostic import DiagnosticCommand

class TracerouteSimulatorShell(cmd2.Cmd):
    def __init__(self):
        # ...
        self.register_command_set(DiagnosticCommand(self))
```

### Command Completion

Location: `src/shell/completers/dynamic.py`

```python
class DynamicCompleter:
    """Dynamic tab completion for shell commands."""
    
    def __init__(self, shell):
        self.shell = shell
        
    def complete_ips(self, text: str, line: str, 
                    begidx: int, endidx: int) -> List[str]:
        """Complete IP addresses from known routers."""
        all_ips = set()
        
        # Collect IPs from all routers
        for router in self.shell.simulator.routers.values():
            for iface in router.get('interfaces', {}).values():
                for addr in iface.get('addresses', []):
                    ip = addr.split('/')[0]
                    all_ips.add(ip)
                    
        # Filter by prefix
        return [ip for ip in all_ips if ip.startswith(text)]
        
    def complete_routers(self, text: str, line: str,
                        begidx: int, endidx: int) -> List[str]:
        """Complete router names."""
        routers = self.shell.simulator.routers.keys()
        return [r for r in routers if r.startswith(text)]
```

## Firewall Analysis Engine

### IptablesForwardAnalyzer

Location: `src/analyzers/iptables_forward_analyzer.py`

```python
class IptablesForwardAnalyzer:
    """Analyzes iptables FORWARD chain for packet filtering decisions."""
    
    def analyze_packet(self, router_facts: dict, packet: dict) -> dict:
        """
        Analyze if packet would be forwarded.
        
        Args:
            router_facts: Router configuration including iptables
            packet: {
                'source_ip': str,
                'dest_ip': str,
                'protocol': str,
                'source_port': int,
                'dest_port': int,
                'in_interface': str,
                'out_interface': str
            }
            
        Returns:
            {
                'allowed': bool,
                'matching_rule': str,
                'chain_traversal': list,
                'packet_counts': dict
            }
        """
        # Get FORWARD chain rules
        forward_chain = self._get_chain(router_facts, 'FORWARD')
        
        # Process rules in order
        for rule in forward_chain:
            if self._rule_matches(rule, packet):
                return self._process_rule_action(rule)
                
        # Default policy
        return self._get_default_policy(router_facts)
```

### Rule Matching Logic

```python
def _rule_matches(self, rule: dict, packet: dict) -> bool:
    """
    Check if iptables rule matches packet.
    
    Implements full iptables matching logic:
    - IP address matching (source/dest)
    - Interface matching (in/out)
    - Protocol matching
    - Port matching
    - State matching
    - Ipset matching
    """
    
    # Source IP match
    if rule.get('source'):
        if not self._ip_in_range(packet['source_ip'], rule['source']):
            return False
            
    # Destination IP match
    if rule.get('destination'):
        if not self._ip_in_range(packet['dest_ip'], rule['destination']):
            return False
            
    # Protocol match
    if rule.get('protocol'):
        if packet['protocol'] != rule['protocol']:
            return False
            
    # Port matches (for TCP/UDP)
    if packet['protocol'] in ['tcp', 'udp']:
        if rule.get('source_port'):
            if not self._port_matches(packet['source_port'], 
                                     rule['source_port']):
                return False
                
    # All conditions matched
    return True
```

### Ipset Integration

```python
def _check_ipset_match(self, set_name: str, ip: str, 
                       port: int = None) -> bool:
    """
    Check if IP/port matches ipset.
    
    Supports:
    - hash:ip sets
    - hash:net sets  
    - hash:ip,port sets
    - bitmap:port sets
    """
    ipset_data = self.router_facts.get('ipsets', {}).get(set_name, {})
    set_type = ipset_data.get('type', '')
    
    if set_type == 'hash:ip':
        return ip in ipset_data.get('members', [])
        
    elif set_type == 'hash:net':
        for network in ipset_data.get('members', []):
            if self._ip_in_network(ip, network):
                return True
                
    elif set_type == 'hash:ip,port':
        member = f"{ip},{port}"
        return member in ipset_data.get('members', [])
        
    return False
```

## Network Namespace Management

### NetworkNamespaceManager

Location: `src/simulators/network_namespace_manager.py`

```python
class NetworkNamespaceManager:
    """Manages Linux network namespaces for simulation."""
    
    def __init__(self, facts_dir: str):
        self.facts_dir = facts_dir
        self.namespaces = {}
        self.veth_pairs = []
        self.bridges = {}
        
    def setup_network(self, verbose: int = 0):
        """
        Create complete network simulation.
        
        Steps:
        1. Create namespaces for each router
        2. Create veth pairs for connections
        3. Configure IP addresses
        4. Set up routing tables
        5. Apply firewall rules
        6. Create bridges where needed
        """
        
        # Load router facts
        routers = self._load_router_facts()
        
        # Phase 1: Create namespaces
        for router_name, facts in routers.items():
            self._create_namespace(router_name)
            
        # Phase 2: Create connections
        connections = self._analyze_connections(routers)
        for conn in connections:
            self._create_veth_pair(conn)
            
        # Phase 3: Configure routers
        for router_name, facts in routers.items():
            self._configure_router(router_name, facts)
```

### Namespace Operations

```python
def _create_namespace(self, name: str):
    """Create network namespace."""
    cmd = ['ip', 'netns', 'add', name]
    subprocess.run(cmd, check=True)
    
    # Enable loopback
    subprocess.run(['ip', 'netns', 'exec', name, 
                   'ip', 'link', 'set', 'lo', 'up'])
    
def _create_veth_pair(self, connection: dict):
    """
    Create virtual ethernet pair between namespaces.
    
    Args:
        connection: {
            'router1': str,
            'iface1': str,
            'router2': str,
            'iface2': str
        }
    """
    # Generate unique veth names
    veth1 = f"veth-{connection['router1']}-{connection['iface1']}"
    veth2 = f"veth-{connection['router2']}-{connection['iface2']}"
    
    # Create veth pair
    cmd = ['ip', 'link', 'add', veth1, 'type', 'veth', 'peer', 'name', veth2]
    subprocess.run(cmd, check=True)
    
    # Move to namespaces
    subprocess.run(['ip', 'link', 'set', veth1, 'netns', connection['router1']])
    subprocess.run(['ip', 'link', 'set', veth2, 'netns', connection['router2']])
    
    # Rename to match expected interface names
    self._rename_interface(connection['router1'], veth1, connection['iface1'])
    self._rename_interface(connection['router2'], veth2, connection['iface2'])
```

### Bridge Configuration

```python
def _setup_bridge(self, namespace: str, bridge_name: str, 
                 interfaces: List[str]):
    """
    Create bridge and add interfaces.
    
    Used for routers connecting multiple networks
    on the same L2 segment.
    """
    # Create bridge
    cmd = ['ip', 'netns', 'exec', namespace,
           'ip', 'link', 'add', bridge_name, 'type', 'bridge']
    subprocess.run(cmd, check=True)
    
    # Add interfaces to bridge
    for iface in interfaces:
        cmd = ['ip', 'netns', 'exec', namespace,
               'ip', 'link', 'set', iface, 'master', bridge_name]
        subprocess.run(cmd, check=True)
        
    # Bring up bridge
    cmd = ['ip', 'netns', 'exec', namespace,
           'ip', 'link', 'set', bridge_name, 'up']
    subprocess.run(cmd, check=True)
```

### Firewall Configuration

```python
def _apply_iptables_rules(self, namespace: str, rules: dict):
    """
    Apply iptables rules to namespace.
    
    Handles:
    - All standard chains (INPUT, OUTPUT, FORWARD, etc.)
    - Custom chains
    - Rule ordering
    - Default policies
    """
    
    # Set default policies
    for chain, policy in rules.get('policies', {}).items():
        cmd = ['ip', 'netns', 'exec', namespace,
               'iptables', '-P', chain, policy]
        subprocess.run(cmd, check=True)
        
    # Create custom chains
    for chain_name in rules.get('custom_chains', []):
        cmd = ['ip', 'netns', 'exec', namespace,
               'iptables', '-N', chain_name]
        subprocess.run(cmd, check=True)
        
    # Apply rules in order
    for rule in rules.get('rules', []):
        cmd = self._build_iptables_command(namespace, rule)
        subprocess.run(cmd, check=True)
```

## Data Models and Storage

### Facts Schema

Location: `src/core/models.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Optional

@dataclass
class Interface:
    """Network interface model."""
    name: str
    addresses: List[str]
    state: str
    mtu: int = 1500
    flags: List[str] = None
    
@dataclass
class Route:
    """Routing table entry."""
    destination: str
    gateway: Optional[str]
    interface: str
    metric: int = 0
    table: str = 'main'
    scope: str = 'global'
    
@dataclass
class IptablesRule:
    """Iptables rule model."""
    chain: str
    table: str = 'filter'
    source: Optional[str] = None
    destination: Optional[str] = None
    protocol: Optional[str] = None
    in_interface: Optional[str] = None
    out_interface: Optional[str] = None
    action: str = 'ACCEPT'
    matches: Dict = None
    
@dataclass
class Router:
    """Router configuration model."""
    hostname: str
    interfaces: Dict[str, Interface]
    routes: List[Route]
    iptables: Dict[str, List[IptablesRule]]
    metadata: Dict
    ipsets: Dict = None
    ip_rules: List = None
```

### Shared Memory Management

Location: `src/core/tsim_shm_manager.py`

```python
class TsimShmManager:
    """
    Manages shared memory for inter-process communication.
    
    Used for:
    - Service registration across namespaces
    - Host registry
    - Namespace status tracking
    """
    
    def __init__(self, namespace: str = "tsim"):
        self.namespace = namespace
        self.shm_dir = f"/dev/shm/{namespace}"
        self._ensure_directory()
        
    def write(self, key: str, data: dict):
        """Write data to shared memory."""
        path = os.path.join(self.shm_dir, f"{key}.json")
        with open(path, 'w') as f:
            json.dump(data, f)
            
    def read(self, key: str) -> dict:
        """Read data from shared memory."""
        path = os.path.join(self.shm_dir, f"{key}.json")
        if os.path.exists(path):
            with open(path, 'r') as f:
                return json.load(f)
        return {}
        
    def list_keys(self, pattern: str = "*") -> List[str]:
        """List all keys matching pattern."""
        import glob
        files = glob.glob(os.path.join(self.shm_dir, f"{pattern}.json"))
        return [os.path.basename(f)[:-5] for f in files]
```

### Configuration Management

```python
class ConfigManager:
    """Manages application configuration."""
    
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self) -> dict:
        """
        Load configuration from (in order):
        1. Environment variable path
        2. ~/.traceroute_simulator.yaml
        3. ./traceroute_simulator.yaml
        4. Default configuration
        """
        config_paths = [
            os.environ.get('TRACEROUTE_SIMULATOR_CONF'),
            os.path.expanduser('~/.traceroute_simulator.yaml'),
            './traceroute_simulator.yaml'
        ]
        
        for path in config_paths:
            if path and os.path.exists(path):
                with open(path) as f:
                    return yaml.safe_load(f)
                    
        return self._default_config()
```

## Testing Framework

### Test Structure

```python
# tests/test_traceroute_simulator.py
import pytest
from src.core.traceroute_simulator import TracerouteSimulator

class TestTracerouteSimulator:
    """Test suite for TracerouteSimulator."""
    
    @pytest.fixture
    def simulator(self):
        """Create simulator with test data."""
        return TracerouteSimulator('tests/tsim_facts')
        
    def test_simple_path(self, simulator):
        """Test basic path tracing."""
        path = simulator.simulate_traceroute('10.1.1.1', '10.2.1.1')
        assert len(path) == 3
        assert path[0]['router'] == 'hq-gw'
        assert path[-1]['router'] == 'br-gw'
        
    def test_no_route(self, simulator):
        """Test handling of unreachable destination."""
        with pytest.raises(NoRouteError):
            simulator.simulate_traceroute('10.1.1.1', '192.168.1.1')
            
    @pytest.mark.parametrize('source,dest,expected_hops', [
        ('10.1.1.1', '10.2.1.1', 3),
        ('10.1.1.1', '10.3.1.1', 4),
        ('10.2.1.1', '10.3.1.1', 3),
    ])
    def test_various_paths(self, simulator, source, dest, expected_hops):
        """Test multiple path combinations."""
        path = simulator.simulate_traceroute(source, dest)
        assert len(path) == expected_hops
```

### Integration Testing

```python
# tests/test_namespace_integration.py
import pytest
import subprocess

class TestNamespaceIntegration:
    """Integration tests requiring namespace setup."""
    
    @pytest.fixture(scope='class')
    def namespace_network(self):
        """Setup namespace network for testing."""
        # Setup
        subprocess.run(['sudo', 'make', 'netsetup'], check=True)
        yield
        # Teardown
        subprocess.run(['sudo', 'make', 'netclean'], check=True)
        
    def test_ping_connectivity(self, namespace_network):
        """Test ICMP connectivity in namespace."""
        result = subprocess.run(
            ['sudo', 'ip', 'netns', 'exec', 'hq-gw', 
             'ping', '-c', '1', '10.2.1.1'],
            capture_output=True
        )
        assert result.returncode == 0
        
    def test_service_connectivity(self, namespace_network):
        """Test TCP service connectivity."""
        # Start service
        subprocess.run(['sudo', 'make', 'svcstart', 
                       'ARGS=10.1.1.1:8080'])
        
        # Test connection
        result = subprocess.run(
            ['sudo', 'make', 'svctest',
             'ARGS=-s 10.2.1.1 -d 10.1.1.1:8080'],
            capture_output=True
        )
        assert b'Connection successful' in result.stdout
```

### Mock Testing

```python
# tests/test_with_mocks.py
from unittest.mock import Mock, patch
import pytest

class TestWithMocks:
    """Tests using mocks for external dependencies."""
    
    @patch('subprocess.run')
    def test_mtr_execution(self, mock_run):
        """Test MTR executor with mocked subprocess."""
        mock_run.return_value.stdout = "mtr output"
        mock_run.return_value.returncode = 0
        
        from src.executors.mtr_executor import MTRExecutor
        executor = MTRExecutor()
        result = executor.execute('10.1.1.1', '10.2.1.1')
        
        assert result == "mtr output"
        mock_run.assert_called_once()
        
    @patch('src.core.traceroute_simulator.TracerouteSimulator._load_routers')
    def test_with_custom_routers(self, mock_load):
        """Test with programmatically created routers."""
        mock_load.return_value = {
            'test-router': {
                'hostname': 'test-router',
                'interfaces': {
                    'eth0': {
                        'addresses': ['10.0.0.1/24']
                    }
                }
            }
        }
        
        simulator = TracerouteSimulator()
        assert 'test-router' in simulator.routers
```

## Extension Points

### Adding New Protocols

```python
# src/analyzers/protocol_analyzer.py
class ProtocolAnalyzer:
    """Base class for protocol-specific analysis."""
    
    @abstractmethod
    def analyze(self, packet: dict, rule: dict) -> bool:
        """Check if rule matches packet for this protocol."""
        pass
        
class TCPAnalyzer(ProtocolAnalyzer):
    """TCP-specific analysis."""
    
    def analyze(self, packet: dict, rule: dict) -> bool:
        # Check TCP flags
        if rule.get('tcp_flags'):
            if not self._check_tcp_flags(packet, rule['tcp_flags']):
                return False
                
        # Check port ranges
        if rule.get('source_ports'):
            if packet['source_port'] not in rule['source_ports']:
                return False
                
        return True
        
# Register analyzer
PROTOCOL_ANALYZERS = {
    'tcp': TCPAnalyzer(),
    'udp': UDPAnalyzer(),
    'icmp': ICMPAnalyzer(),
    # Add new protocols here
}
```

### Custom Facts Sources

```python
# src/core/facts_loader.py
class FactsLoader:
    """Extensible facts loading system."""
    
    def __init__(self):
        self.sources = []
        
    def register_source(self, source: 'FactsSource'):
        """Register a new facts source."""
        self.sources.append(source)
        
    def load_facts(self) -> dict:
        """Load facts from all sources."""
        facts = {}
        for source in self.sources:
            facts.update(source.load())
        return facts
        
class JSONFactsSource:
    """Load facts from JSON files."""
    
    def load(self) -> dict:
        # Implementation
        pass
        
class DatabaseFactsSource:
    """Load facts from database."""
    
    def load(self) -> dict:
        # Implementation
        pass
        
class APIFactsSource:
    """Load facts from REST API."""
    
    def load(self) -> dict:
        # Implementation
        pass
```

### Output Formatters

```python
# src/core/formatters.py
class OutputFormatterRegistry:
    """Registry for output formatters."""
    
    formatters = {}
    
    @classmethod
    def register(cls, name: str, formatter: 'OutputFormatter'):
        """Register a new formatter."""
        cls.formatters[name] = formatter
        
    @classmethod
    def get_formatter(cls, name: str) -> 'OutputFormatter':
        """Get formatter by name."""
        return cls.formatters.get(name, TextFormatter())
        
# Register built-in formatters
OutputFormatterRegistry.register('json', JSONFormatter())
OutputFormatterRegistry.register('text', TextFormatter())
OutputFormatterRegistry.register('yaml', YAMLFormatter())
OutputFormatterRegistry.register('table', TableFormatter())

# Add custom formatter
class GraphMLFormatter(OutputFormatter):
    """Format output as GraphML for network visualization."""
    
    def format(self, data: dict) -> str:
        # Convert to GraphML format
        pass
        
OutputFormatterRegistry.register('graphml', GraphMLFormatter())
```

## Development Workflow

### Setting Up Development Environment

```bash
# Clone repository
git clone <repository>
cd traceroute-simulator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e .
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install
```

### Development Configuration

```python
# .env for development
TRACEROUTE_SIMULATOR_FACTS=tests/tsim_facts
TRACEROUTE_SIMULATOR_RAW_FACTS=tests/raw_facts
TRACEROUTE_SIMULATOR_DEBUG=1
PYTHONDONTWRITEBYTECODE=1
PYTHONUNBUFFERED=1
```

### Code Style Guidelines

```python
"""
Follow PEP 8 with these additions:
- Line length: 100 characters
- Docstrings: Google style
- Type hints: Use for all public methods
- Import order: stdlib, third-party, local
"""

from typing import List, Dict, Optional  # Type hints
import os  # Standard library
import sys

import yaml  # Third-party
import networkx as nx

from src.core.models import Router  # Local imports
from src.utils.helpers import validate_ip


class ExampleClass:
    """One-line summary.
    
    Longer description if needed.
    
    Attributes:
        name: Description of name attribute.
        routers: Dictionary of router configurations.
    """
    
    def example_method(self, ip: str, port: int = 80) -> Dict[str, any]:
        """Short description.
        
        Args:
            ip: IP address to process.
            port: Port number (default: 80).
            
        Returns:
            Dictionary containing results.
            
        Raises:
            ValueError: If IP is invalid.
        """
        pass
```

### Adding New Features

1. **Create Feature Branch**
```bash
git checkout -b feature/new-capability
```

2. **Implement Feature**
```python
# src/core/new_feature.py
class NewFeature:
    """Implementation of new capability."""
    pass
```

3. **Add Tests**
```python
# tests/test_new_feature.py
def test_new_feature():
    """Test the new capability."""
    pass
```

4. **Update Documentation**
```markdown
# docs/new_feature.md
## New Feature Documentation
```

5. **Run Tests**
```bash
make test
pytest tests/test_new_feature.py -v
```

6. **Submit PR**
```bash
git add .
git commit -m "feat: Add new capability for X"
git push origin feature/new-capability
```

### Debugging Techniques

```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Use debugger
import pdb; pdb.set_trace()

# IPython for interactive debugging
from IPython import embed; embed()

# Print debug information
if os.environ.get('TRACEROUTE_SIMULATOR_DEBUG'):
    print(f"DEBUG: Processing router {router_name}")
    
# Assertions for development
assert router is not None, f"Router {name} not found"
```

### Performance Profiling

```python
# Profile code execution
import cProfile
import pstats

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Code to profile
    simulator.simulate_traceroute('10.1.1.1', '10.2.1.1')
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
```

### Common Development Tasks

```bash
# Run specific test
pytest tests/test_traceroute_simulator.py::TestTracerouteSimulator::test_simple_path

# Run with coverage
pytest --cov=src --cov-report=html

# Check code style
flake8 src/
black --check src/

# Generate documentation
sphinx-build -b html docs/ docs/_build/

# Build package
python setup.py sdist bdist_wheel

# Clean up
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

### Troubleshooting Development Issues

```python
# Common import issues
"""
If imports fail, check:
1. PYTHONPATH includes src/
2. __init__.py files exist
3. Circular imports
"""

# Fix: Add to top of script
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Memory leaks in namespace operations
"""
Always clean up subprocess handles and namespace resources
"""
import subprocess
import contextlib

@contextlib.contextmanager
def namespace_exec(namespace: str):
    """Context manager for namespace operations."""
    process = None
    try:
        process = subprocess.Popen(...)
        yield process
    finally:
        if process:
            process.terminate()
            process.wait()
```
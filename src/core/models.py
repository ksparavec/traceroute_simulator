#!/usr/bin/env -S python3 -B -u
"""
Data Models for Traceroute Simulator

This module provides type-safe data models using dataclasses and type hints
for all core data structures in the traceroute simulator.

Key Features:
- Type-safe data structures with validation
- Immutable models where appropriate
- JSON serialization support
- Clear documentation of all fields
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Union, Tuple
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from enum import Enum
import json
from pathlib import Path


# Type aliases for clarity
IPAddress = Union[IPv4Address, IPv6Address]
IPNetwork = Union[IPv4Network, IPv6Network]


class RouterType(str, Enum):
    """Router type classification."""
    GATEWAY = "gateway"
    CORE = "core"
    ACCESS = "access"
    NONE = "none"


class RouterLocation(str, Enum):
    """Router location classification."""
    HQ = "hq"
    BRANCH = "branch"
    DATACENTER = "datacenter"
    NONE = "none"


class RouterRole(str, Enum):
    """Router role classification."""
    GATEWAY = "gateway"
    DISTRIBUTION = "distribution"
    SERVER = "server"
    WIFI = "wifi"
    DMZ = "dmz"
    LAB = "lab"
    NONE = "none"


class RouteType(str, Enum):
    """Route type classification."""
    UNICAST = "unicast"
    LOCAL = "local"
    BROADCAST = "broadcast"
    MULTICAST = "multicast"
    BLACKHOLE = "blackhole"
    UNREACHABLE = "unreachable"
    PROHIBIT = "prohibit"


class RouteProtocol(str, Enum):
    """Routing protocol classification."""
    KERNEL = "kernel"
    BOOT = "boot"
    STATIC = "static"
    BGP = "bgp"
    OSPF = "ospf"
    RIP = "rip"
    DHCP = "dhcp"


class RouteScope(str, Enum):
    """Route scope classification."""
    GLOBAL = "global"
    LINK = "link"
    HOST = "host"
    SITE = "site"


@dataclass(frozen=True)
class Route:
    """
    Represents a single routing table entry.
    
    Immutable data structure for type-safe route handling.
    """
    destination: str  # Keep as string for flexibility (can be "default", IP, or network)
    interface: str
    gateway: Optional[str] = None
    metric: int = 0
    preferred_source: Optional[str] = None
    protocol: RouteProtocol = RouteProtocol.KERNEL
    scope: RouteScope = RouteScope.GLOBAL
    route_type: RouteType = RouteType.UNICAST
    table: str = "main"
    flags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Validate route data after initialization."""
        # Validate destination
        if self.destination not in ["default", "::/0", "0.0.0.0/0"]:
            try:
                if "/" in self.destination:
                    ip_network(self.destination, strict=False)
                else:
                    ip_address(self.destination)
            except ValueError as e:
                raise ValueError(f"Invalid destination: {self.destination}") from e
                
        # Validate gateway if present
        if self.gateway:
            try:
                ip_address(self.gateway)
            except ValueError as e:
                raise ValueError(f"Invalid gateway: {self.gateway}") from e
                
        # Validate preferred source if present
        if self.preferred_source:
            try:
                ip_address(self.preferred_source)
            except ValueError as e:
                raise ValueError(f"Invalid preferred source: {self.preferred_source}") from e
    
    def matches_destination(self, dst_ip: str) -> Tuple[bool, int]:
        """
        Check if this route matches the destination IP.
        
        Args:
            dst_ip: Destination IP address to check
            
        Returns:
            Tuple of (matches, prefix_length)
        """
        try:
            dst_addr = ip_address(dst_ip)
        except ValueError:
            return False, -1
            
        # Handle default route
        if self.destination in ["default", "0.0.0.0/0", "::/0"]:
            return True, 0
            
        # Handle network routes
        if "/" in self.destination:
            try:
                network = ip_network(self.destination, strict=False)
                if dst_addr in network:
                    return True, network.prefixlen
            except ValueError:
                pass
                
        # Handle host routes
        try:
            route_addr = ip_address(self.destination)
            if dst_addr == route_addr:
                return True, 32 if dst_addr.version == 4 else 128
        except ValueError:
            pass
            
        return False, -1
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Route":
        """Create Route from dictionary representation."""
        # Map JSON fields to dataclass fields
        return cls(
            destination=data.get("dst", "default"),
            interface=data["dev"],
            gateway=data.get("gateway"),
            metric=data.get("metric", 0),
            preferred_source=data.get("prefsrc"),
            protocol=RouteProtocol(data.get("protocol", "kernel")),
            scope=RouteScope(data.get("scope", "global")),
            route_type=RouteType(data.get("type", "unicast")),
            table=data.get("table", "main"),
            flags=data.get("flags", [])
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Route to dictionary representation."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(frozen=True)
class PolicyRule:
    """
    Represents a policy routing rule.
    
    Immutable data structure for ip rule entries.
    """
    priority: int
    selector: Dict[str, Any]  # from, to, iif, oif, etc.
    action: str  # lookup, blackhole, unreachable, etc.
    table: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyRule":
        """Create PolicyRule from dictionary representation."""
        return cls(
            priority=data["priority"],
            selector={k: v for k, v in data.items() if k not in ["priority", "action", "table"]},
            action=data.get("action", "lookup"),
            table=data.get("table")
        )


@dataclass(frozen=True)
class RouterMetadata:
    """
    Router metadata for classification and capabilities.
    
    Immutable data structure for router properties.
    """
    linux: bool = True
    router_type: RouterType = RouterType.NONE
    location: RouterLocation = RouterLocation.NONE
    role: RouterRole = RouterRole.NONE
    vendor: str = "linux"
    manageable: bool = True
    ansible_controller: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RouterMetadata":
        """Create RouterMetadata from dictionary representation."""
        return cls(
            linux=data.get("linux", True),
            router_type=RouterType(data.get("type", "none")),
            location=RouterLocation(data.get("location", "none")),
            role=RouterRole(data.get("role", "none")),
            vendor=data.get("vendor", "linux"),
            manageable=data.get("manageable", True),
            ansible_controller=data.get("ansible_controller", False)
        )
    
    def is_gateway(self) -> bool:
        """Check if router is a gateway type."""
        return self.router_type == RouterType.GATEWAY
    
    def can_reach_internet(self) -> bool:
        """Check if router can reach internet destinations."""
        return self.is_gateway()


@dataclass
class Interface:
    """
    Represents a network interface.
    
    Mutable as interfaces can change state.
    """
    name: str
    ip_address: Optional[str] = None
    network: Optional[str] = None
    mac_address: Optional[str] = None
    mtu: int = 1500
    state: str = "up"
    flags: List[str] = field(default_factory=list)
    
    def is_up(self) -> bool:
        """Check if interface is up."""
        return self.state.lower() == "up" and "UP" in self.flags


@dataclass
class TracerouteHop:
    """
    Represents a single hop in a traceroute path.
    
    Mutable to allow updates during path construction.
    """
    hop_number: int
    router_name: str
    ip_address: str
    incoming_interface: Optional[str] = None
    outgoing_interface: Optional[str] = None
    is_router_owned: bool = True
    rtt: float = 0.0
    
    def format_display(self) -> str:
        """Format hop for display."""
        if self.incoming_interface and self.outgoing_interface:
            return f"{self.router_name} ({self.ip_address}) from {self.incoming_interface} to {self.outgoing_interface}"
        elif self.incoming_interface:
            return f"{self.router_name} ({self.ip_address}) on {self.incoming_interface}"
        else:
            return f"{self.router_name} ({self.ip_address})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hop": self.hop_number,
            "router_name": self.router_name,
            "ip_address": self.ip_address,
            "interface": self.incoming_interface or "",
            "is_router_owned": self.is_router_owned,
            "connected_router": "",  # For compatibility
            "outgoing_interface": self.outgoing_interface or "",
            "rtt": self.rtt
        }


@dataclass
class TraceroutePath:
    """
    Represents a complete traceroute path.
    
    Provides methods for path manipulation and analysis.
    """
    source: str
    destination: str
    hops: List[TracerouteHop] = field(default_factory=list)
    is_complete: bool = False
    error: Optional[str] = None
    
    def add_hop(self, hop: TracerouteHop) -> None:
        """Add a hop to the path."""
        self.hops.append(hop)
        
    def get_last_hop(self) -> Optional[TracerouteHop]:
        """Get the last hop in the path."""
        return self.hops[-1] if self.hops else None
    
    def get_hop_count(self) -> int:
        """Get the number of hops."""
        return len(self.hops)
    
    def get_total_rtt(self) -> float:
        """Calculate total RTT for the path."""
        return sum(hop.rtt for hop in self.hops)
    
    def format_text(self) -> str:
        """Format path as text output."""
        lines = [f"traceroute to {self.destination} from {self.source}"]
        for hop in self.hops:
            rtt_str = f" {hop.rtt:.1f}ms" if hop.rtt > 0 else ""
            lines.append(f"  {hop.hop_number}  {hop.format_display()}{rtt_str}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source,
            "destination": self.destination,
            "traceroute_path": [hop.to_dict() for hop in self.hops],
            "is_complete": self.is_complete,
            "error": self.error
        }
    
    def to_json(self, indent: Optional[int] = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class IptablesRule:
    """
    Represents an iptables rule.
    
    Supports complex matching conditions and actions.
    """
    chain: str
    target: str
    protocol: Optional[str] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    in_interface: Optional[str] = None
    out_interface: Optional[str] = None
    source_port: Optional[str] = None
    destination_port: Optional[str] = None
    match_extensions: Dict[str, Any] = field(default_factory=dict)
    jump_target: Optional[str] = None
    
    def matches_packet(
        self,
        src_ip: str,
        dst_ip: str,
        protocol: str = "all",
        src_port: Optional[int] = None,
        dst_port: Optional[int] = None,
        in_iface: Optional[str] = None,
        out_iface: Optional[str] = None
    ) -> bool:
        """
        Check if this rule matches a packet.
        
        Args:
            src_ip: Source IP address
            dst_ip: Destination IP address
            protocol: Protocol (tcp, udp, icmp, all)
            src_port: Source port (optional)
            dst_port: Destination port (optional)
            in_iface: Incoming interface (optional)
            out_iface: Outgoing interface (optional)
            
        Returns:
            True if rule matches the packet
        """
        # Check protocol
        if self.protocol and self.protocol != "all" and protocol != "all":
            if self.protocol != protocol:
                return False
                
        # Check source IP
        if self.source and self.source != "0.0.0.0/0":
            try:
                src_addr = ip_address(src_ip)
                src_net = ip_network(self.source, strict=False)
                if src_addr not in src_net:
                    return False
            except ValueError:
                return False
                
        # Check destination IP
        if self.destination and self.destination != "0.0.0.0/0":
            try:
                dst_addr = ip_address(dst_ip)
                dst_net = ip_network(self.destination, strict=False)
                if dst_addr not in dst_net:
                    return False
            except ValueError:
                return False
                
        # Check interfaces
        if self.in_interface and in_iface and self.in_interface != in_iface:
            return False
        if self.out_interface and out_iface and self.out_interface != out_iface:
            return False
            
        # Check ports
        if self.source_port and src_port:
            if not self._port_matches(src_port, self.source_port):
                return False
        if self.destination_port and dst_port:
            if not self._port_matches(dst_port, self.destination_port):
                return False
                
        return True
    
    def _port_matches(self, port: int, port_spec: str) -> bool:
        """Check if port matches port specification."""
        if ":" in port_spec:
            # Range
            start, end = map(int, port_spec.split(":"))
            return start <= port <= end
        elif "," in port_spec:
            # List
            return str(port) in port_spec.split(",")
        else:
            # Single port
            return port == int(port_spec)


@dataclass
class NetworkNamespace:
    """
    Represents a Linux network namespace configuration.
    """
    name: str
    interfaces: List[Interface] = field(default_factory=list)
    routes: List[Route] = field(default_factory=list)
    rules: List[PolicyRule] = field(default_factory=list)
    iptables_rules: List[IptablesRule] = field(default_factory=list)
    ipsets: Dict[str, List[str]] = field(default_factory=dict)
    
    def get_interface(self, name: str) -> Optional[Interface]:
        """Get interface by name."""
        return next((iface for iface in self.interfaces if iface.name == name), None)
    
    def get_routes_for_destination(self, dst_ip: str) -> List[Tuple[Route, int]]:
        """Get all routes matching destination, sorted by prefix length."""
        matches = []
        for route in self.routes:
            match, prefix_len = route.matches_destination(dst_ip)
            if match:
                matches.append((route, prefix_len))
        return sorted(matches, key=lambda x: x[1], reverse=True)
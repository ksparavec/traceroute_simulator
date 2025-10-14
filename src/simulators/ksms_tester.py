#!/usr/bin/env -S python3 -B -u
"""
KSMS Tester backend: Fast YES/NO service reachability per router

Implements PREROUTING/POSTROUTING counter taps, static neighbor configuration,
and a single userspace probe helper (TCP SYN / UDP datagram) emitted from the source netns.
Routers to test are derived from registries based on the source IP, analogous to
other tsimsh commands.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from tsim.core.config_loader import get_registry_paths

# Global verbosity level
VERBOSE = 0

# Global registry manager instance
REGISTRY_MGR = None

def _dbg(msg: str, level: int = 1):
    """Debug output that respects verbosity level."""
    global VERBOSE
    if VERBOSE >= level:
        print(msg, file=sys.stderr)


def _sudo_wrap(cmd: List[str]) -> List[str]:
    return (['sudo', '-n'] + cmd) if os.geteuid() != 0 else cmd


def run(cmd: List[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    # When text=True, subprocess expects string input, not bytes
    # So we pass the string directly without encoding
    result = subprocess.run(_sudo_wrap(cmd), input=input_data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0 and VERBOSE >= 2:
        _dbg(f"[WARN] Command failed with code {result.returncode}: {' '.join(cmd[:3])}...", 2)
        if VERBOSE >= 3 and result.stderr:
            _dbg(f"[DEBUG] stderr: {result.stderr}", 3)
    return result


def load_registries() -> Tuple[Dict, Dict]:
    paths = get_registry_paths()
    bridges = {}
    hosts = {}
    try:
        p = Path(paths['bridges'])
        if p.exists():
            bridges = json.load(open(p, 'r'))
    except Exception:
        pass
    try:
        p = Path(paths['hosts'])
        if p.exists():
            hosts = json.load(open(p, 'r'))
    except Exception:
        pass
    return bridges, hosts


def build_ip_to_namespaces(bridges: Dict, hosts: Dict) -> Dict[str, List[str]]:
    ip_map: Dict[str, List[str]] = {}
    # routers from bridges
    for _, binfo in bridges.items():
        for rname, rinfo in binfo.get('routers', {}).items():
            ip_cidr = rinfo.get('ipv4', '')
            if '/' in ip_cidr:
                ip = ip_cidr.split('/')[0]
                if ip and ip != '127.0.0.1':
                    ip_map.setdefault(ip, []).append(rname)
        for hname, hinfo in binfo.get('hosts', {}).items():
            ip_cidr = hinfo.get('ipv4', '')
            if '/' in ip_cidr:
                ip = ip_cidr.split('/')[0]
                if ip and ip != '127.0.0.1':
                    ip_map.setdefault(ip, []).append(hname)
    # hosts registry for primary/secondary
    for hname, hinfo in hosts.items():
        ip_cidr = hinfo.get('primary_ip', '')
        if '/' in ip_cidr:
            ip = ip_cidr.split('/')[0]
            if ip and ip != '127.0.0.1':
                ip_map.setdefault(ip, []).append(hname)
        for sec in hinfo.get('secondary_ips', []):
            if '/' in sec:
                ip = sec.split('/')[0]
                if ip and ip != '127.0.0.1':
                    ip_map.setdefault(ip, []).append(hname)
    # dedupe lists
    for k in list(ip_map.keys()):
        seen = set()
        ip_map[k] = [x for x in ip_map[k] if not (x in seen or seen.add(x))]
    return ip_map


def infer_routers_for_source(src_ip: str, bridges: Dict, hosts: Dict, ip_map: Dict[str, List[str]]) -> List[str]:
    """Infer routers involved for a given source IP using registries, like other commands do.
    Strategy: if source maps to host namespace(s), pick their connected routers from host registry.
    If source maps to a router namespace, include that router.
    """
    ns_list = ip_map.get(src_ip, [])
    routers: List[str] = []
    for ns in ns_list:
        if ns in hosts:
            connected = hosts.get(ns, {}).get('connected_to')
            if connected:
                routers.append(connected)
        else:
            # assume router ns
            routers.append(ns)
    # dedupe
    seen = set()
    routers = [r for r in routers if r and not (r in seen or seen.add(r))]
    return routers


def parse_ports(port_spec: str, default_proto: str, max_services: int, range_limit: int = 100, force: bool = False) -> List[Tuple[int, str]]:
    """Parse port spec using the same logic as WSGI TsimPortParserService.
    Import the service by adding the wsgi dir to sys.path to avoid requiring 'wsgi' as a package.
    """
    try:
        # For large ranges, skip WSGI service and use our enhanced parser
        if range_limit > 100:
            raise Exception("Using enhanced parser for large range limits")
        
        # Project root = .../src/.. (two levels up from this file)
        project_root = Path(__file__).resolve().parents[2]
        wsgi_dir = project_root / 'wsgi'
        if str(wsgi_dir) not in sys.path:
            sys.path.insert(0, str(wsgi_dir))
        from services.tsim_port_parser_service import TsimPortParserService  # type: ignore
        parser = TsimPortParserService()
        return parser.parse_port_spec(port_spec, default_proto, max_services)
    except Exception as e:
        # Fallback: enhanced parser supporting port ranges and WSGI formats
        _dbg(f"[WARN] Falling back to enhanced port parser: {e}", 1)
        result: List[Tuple[int, str]] = []
        
        for part in [p.strip() for p in port_spec.split(',') if p.strip()]:
            # Handle port ranges: 1000-2000/udp or 1000-2000
            if '-' in part and '/' in part:
                # Range with protocol: 1000-2000/udp
                range_part, proto = part.split('/', 1)
                start_str, end_str = range_part.split('-', 1)
                start_port, end_port = int(start_str), int(end_str)
                proto = proto.lower()
                if start_port > end_port:
                    raise ValueError(f"Invalid port range: {start_port}-{end_port}")
                
                range_size = end_port - start_port + 1
                if range_size > range_limit and not force:
                    # Cap the range to the limit if not forced
                    end_port = start_port + range_limit - 1
                
                for port in range(start_port, end_port + 1):
                    result.append((port, proto))
            elif '-' in part:
                # Range with default protocol: 1000-2000
                start_str, end_str = part.split('-', 1)
                start_port, end_port = int(start_str), int(end_str)
                if start_port > end_port:
                    raise ValueError(f"Invalid port range: {start_port}-{end_port}")
                
                range_size = end_port - start_port + 1
                if range_size > range_limit and not force:
                    # Cap the range to the limit if not forced
                    end_port = start_port + range_limit - 1
                
                for port in range(start_port, end_port + 1):
                    result.append((port, default_proto))
            elif '/' in part:
                # Single port with protocol: 80/tcp
                p_str, proto = part.split('/', 1)
                port = int(p_str)
                proto = proto.lower()
                result.append((port, proto))
            else:
                # Single port with default protocol: 80
                port = int(part)
                result.append((port, default_proto))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_result = []
        for item in result:
            if item not in seen:
                seen.add(item)
                unique_result.append(item)
        
        if len(unique_result) > max_services:
            unique_result = unique_result[:max_services]
        return unique_result


def egress_iface_and_nexthop_for(router: str, dst_ip: str) -> Tuple[Optional[str], Optional[str]]:
    """Get egress interface and next hop for destination."""
    # ip netns exec router ip route get <dst>
    cp = run(['ip', 'netns', 'exec', router, 'ip', 'route', 'get', dst_ip])
    if cp.returncode != 0:
        return None, None
    
    line = cp.stdout.splitlines()[0] if cp.stdout else ""
    
    # Extract device
    iface_match = re.search(r'\bdev\s+(\S+)', line)
    iface = iface_match.group(1) if iface_match else None
    
    # Extract next hop (via X.X.X.X)
    via_match = re.search(r'\bvia\s+(\S+)', line)
    nexthop = via_match.group(1) if via_match else None
    
    # If no via, destination is directly connected (use dst_ip as nexthop)
    if not nexthop and iface:
        nexthop = dst_ip
    
    return iface, nexthop


def taps_restore_payload(services: List[Tuple[int, str]], svc_tokens: Dict[Tuple[int, str], Dict], run_id: str) -> str:
    lines = ["*mangle", ":TSIM_TAP_FW - [0:0]"]
    # Ensure user chain returns
    lines.append("-F TSIM_TAP_FW")
    lines.append("-A TSIM_TAP_FW -j RETURN")
    for port, proto in services:
        dscp = svc_tokens[(port, proto)]['dscp']
        comment_pre = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
        comment_post = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"
        lines.append(f"-I PREROUTING 1 -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_pre)}")
        lines.append(f"-I POSTROUTING 1 -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_post)}")
    lines.append("COMMIT")
    return "\n".join(lines) + "\n"


def taps_delete_payload(services: List[Tuple[int, str]], svc_tokens: Dict[Tuple[int, str], Dict], run_id: str) -> str:
    # Reflect inserts with deletes; use -D PREROUTING/POSTROUTING entries
    lines = ["*mangle"]
    for port, proto in services:
        dscp = svc_tokens[(port, proto)]['dscp']
        comment_pre = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
        comment_post = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"
        lines.append(f"-D PREROUTING -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_pre)}")
        lines.append(f"-D POSTROUTING -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_post)}")
    lines.append("COMMIT")
    return "\n".join(lines) + "\n"


def iptables_save_mangle(router: str, with_counters: bool = True) -> str:
    args = ['ip', 'netns', 'exec', router, 'iptables-save']
    if with_counters:
        args.append('-c')
    args.extend(['-t', 'mangle'])
    cp = run(args)
    return cp.stdout if cp.returncode == 0 else ''


def execute_iptables_script(rname: str, script_commands: List[str]) -> 'subprocess.CompletedProcess':
    """Execute iptables commands via temporary shell script.

    Args:
        rname: Router namespace name
        script_commands: List of iptables command strings to execute

    Returns:
        CompletedProcess with returncode, stdout, stderr
    """
    import tempfile

    # Create temporary shell script
    script_content = "#!/bin/bash\nset -e\n" + "\n".join(script_commands) + "\n"

    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        script_path = f.name
        f.write(script_content)

    try:
        # Make executable
        os.chmod(script_path, 0o755)

        # Execute in namespace
        result = run(['ip', 'netns', 'exec', rname, '/bin/bash', script_path])
        return result
    finally:
        # Cleanup
        try:
            os.unlink(script_path)
        except Exception:
            pass


def extract_counter(snapshot: str, comment: str) -> Tuple[int, int]:
    # Lines look like: -A PREROUTING -c <pkts> <bytes> ... -m comment --comment "TSIM_KSMS=..."
    pkts = bytes_ = 0
    found = False
    
    # The comment might be quoted in the saved output
    search_comment = comment.replace('"', '')  # Remove quotes for searching
    
    # Try to find the rule with our exact comment (including run ID)
    for line in snapshot.splitlines():
        # Check if this line contains our specific comment
        # Lines can start with [counters] or just -A
        if search_comment in line and ('-A ' in line):
            # Also verify it's in a comment field (not just random text)
            if '--comment' in line:
                # Extract the actual comment from the line to verify exact match
                comment_match = re.search(r'--comment\s+"([^"]+)"', line)
                if not comment_match:
                    # Try without quotes  
                    comment_match = re.search(r'--comment\s+(\S+)', line)
                
                if comment_match:
                    actual_comment = comment_match.group(1).replace('"', '')
                    if actual_comment == search_comment:
                        found = True
                        # Extract counters - either from [X:Y] at start or -c X Y format
                        if line.startswith('['):
                            m = re.search(r'^\[(\d+):(\d+)\]', line)
                            if m:
                                pkts = int(m.group(1))
                                bytes_ = int(m.group(2))
                        else:
                            m = re.search(r'-c\s+(\d+)\s+(\d+)', line)
                            if m:
                                pkts = int(m.group(1))
                                bytes_ = int(m.group(2))
                        if VERBOSE >= 3:
                            _dbg(f"    [counter] Found exact rule match: '{search_comment[:40]}...' pkts={pkts} bytes={bytes_}", 3)
                        return pkts, bytes_  # Return immediately
    
    if not found and VERBOSE >= 3:
        _dbg(f"    [counter] No matching rule found for comment '{search_comment[:40]}...'", 3)
        # Show what rules we do have with TSIM_KSMS in them
        ksms_lines = [l for l in snapshot.splitlines() if 'TSIM_KSMS' in l and '--comment' in l]
        if ksms_lines:
            _dbg(f"    [counter] Found {len(ksms_lines)} TSIM_KSMS rules in snapshot:", 3)
            for line in ksms_lines[:3]:
                # Extract and show the comment
                comment_match = re.search(r'--comment\s+"([^"]+)"', line)
                if not comment_match:
                    comment_match = re.search(r'--comment\s+(\S+)', line)
                if comment_match:
                    _dbg(f"    [counter]   Comment: {comment_match.group(1)[:60]}...", 3)
    
    return pkts, bytes_


def emit_probes_in_source_ns(source_ns: str, dst_ip: str, services: List[Tuple[int, str]], svc_tokens: Dict[Tuple[int, str], Dict], tcp_timeout: float) -> int:
    # Build a small python helper which sends all probes
    helper = r"""
import socket, sys, json, time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

dst_ip = sys.argv[1]
tcp_timeout = float(sys.argv[2])
spec = json.loads(sys.argv[3])  # list of {port,proto,tos}
verbose = int(sys.argv[4]) if len(sys.argv) > 4 else 0

if verbose >= 2:
    import os
    print(f"[probe] Running in PID {os.getpid()}, sending {len(spec)} probes", file=sys.stderr)

def send_tcp(port, tos):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
        s.settimeout(tcp_timeout)
        if verbose >= 2:
            print(f"[probe] TCP SYN to {dst_ip}:{port} with TOS={tos} (DSCP={tos>>2})", file=sys.stderr)
        try:
            result = s.connect_ex((dst_ip, port))
            if verbose >= 2:
                print(f"[probe] TCP connect_ex result: {result} (111=refused, 110=timeout)", file=sys.stderr)
        except Exception as e:
            if verbose >= 2:
                print(f"[probe] TCP connect exception: {e}", file=sys.stderr)
        s.close()
    except Exception as e:
        if verbose >= 2:
            print(f"[probe] TCP socket error: {e}", file=sys.stderr)

def send_udp(port, tos):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
        if verbose >= 2:
            print(f"[probe] UDP datagram to {dst_ip}:{port} with TOS={tos} (DSCP={tos>>2})", file=sys.stderr)
        bytes_sent = s.sendto(b"x", (dst_ip, port))
        if verbose >= 3:
            print(f"[probe] UDP sent {bytes_sent} bytes", file=sys.stderr)
        s.close()
    except Exception as e:
        if verbose >= 2:
            print(f"[probe] UDP socket error: {e}", file=sys.stderr)

def probe_service(item):
    port = int(item['port'])
    proto = item['proto'] 
    tos = int(item['tos'])
    if proto == 'tcp':
        send_tcp(port, tos)
    else:
        send_udp(port, tos)

# Separate TCP and UDP services for different handling
tcp_services = [item for item in spec if item['proto'] == 'tcp']
udp_services = [item for item in spec if item['proto'] == 'udp']

# Process TCP services with full parallelism (fast, reliable)
tcp_workers = min(100, len(tcp_services)) if tcp_services else 0
if tcp_services:
    with ThreadPoolExecutor(max_workers=tcp_workers) as executor:
        tcp_futures = [executor.submit(probe_service, item) for item in tcp_services]
        for future in as_completed(tcp_futures):
            try:
                future.result()
            except Exception as e:
                if verbose >= 1:
                    print(f"[probe] TCP error in thread: {e}", file=sys.stderr)

# Process UDP services with controlled bursting to reduce packet loss
if udp_services:
    batch_size = 50  # Send UDP in batches of 50
    batch_delay = 0.01  # 10ms delay between batches
    
    for i in range(0, len(udp_services), batch_size):
        batch = udp_services[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(udp_services) + batch_size - 1) // batch_size
        
        if verbose >= 2:
            print(f"[probe] UDP batch {batch_num}/{total_batches}: {len(batch)} packets", file=sys.stderr)
        
        # Process this batch in parallel
        with ThreadPoolExecutor(max_workers=min(50, len(batch))) as executor:
            batch_futures = [executor.submit(probe_service, item) for item in batch]
            for future in as_completed(batch_futures):
                try:
                    future.result()
                except Exception as e:
                    if verbose >= 1:
                        print(f"[probe] UDP error in thread: {e}", file=sys.stderr)
        
        # Small delay between batches (except for last batch)
        if i + batch_size < len(udp_services):
            time.sleep(batch_delay)
"""
    spec = [ {'port': p, 'proto': pr, 'tos': svc_tokens[(p,pr)]['tos']} for (p,pr) in services ]
    argv = ['ip', 'netns', 'exec', source_ns, sys.executable, '-c', helper, dst_ip, str(tcp_timeout), json.dumps(spec), str(VERBOSE)]
    
    if VERBOSE >= 2:
        _dbg(f"  [probe] Executing probe helper in namespace {source_ns}", 2)
        _dbg(f"  [probe] Target: {dst_ip}, Services: {spec}", 2)
    
    cp = run(argv)
    
    if VERBOSE >= 2:
        if cp.stdout:
            _dbg(f"  [probe] stdout: {cp.stdout}", 2)
        if cp.stderr:
            _dbg(f"  [probe] stderr: {cp.stderr}", 2)
        _dbg(f"  [probe] Return code: {cp.returncode}", 2)
    
    return cp.returncode


def main():
    global VERBOSE, REGISTRY_MGR
    ap = argparse.ArgumentParser(
        description='KSMS Tester - Fast YES/NO service reachability testing using kernel-space packet counting',
        epilog='''
Examples:
  # Test single port TCP connectivity
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "80"
  
  # Test multiple TCP ports with verbose output
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "80,443,8080" -v
  
  # Test UDP services
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "53,123" --default-proto udp
  
  # Test mixed protocols (specify per service)
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "80/tcp,53/udp,443/tcp"
  
  # Test port ranges
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "8000-8005/tcp,1000-1010/udp"
  
  # JSON output for automation
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "80,443" -j
  
  # Maximum verbosity for debugging
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "80" -vvv
  
  # Large port range with custom limit and force
  ksms_tester -s 10.1.1.100 -d 10.2.1.200 -P "1000-2000/tcp" --range-limit 1001 --force

The command tests service reachability by:
1. Installing iptables PREROUTING/POSTROUTING counters on involved routers
2. Emitting test probes (TCP SYN or UDP packets) with DSCP marking
3. Analyzing packet counter deltas to determine forwarding behavior
4. Results: YES (forwarded), NO (blocked), UNKNOWN (no packets seen)

Routers are automatically inferred from source IP using network registries.
''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('-s', '--source', required=True, metavar='IP',
                    help='Source IP address')
    ap.add_argument('-d', '--destination', required=True, metavar='IP', 
                    help='Destination IP address')
    ap.add_argument('-P', '--ports', required=True, metavar='PORTS',
                    help='Port specification: "80" or "80,443,8080" or "80/tcp,53/udp" or "1000-2000/udp"')
    ap.add_argument('--default-proto', choices=['tcp','udp'], default='tcp',
                    help='Default protocol when not specified per-port (default: tcp)')
    ap.add_argument('--max-services', type=int, default=10, metavar='N',
                    help='Maximum number of services to test (default: 10)')
    ap.add_argument('--range-limit', type=int, default=100, metavar='N',
                    help='Maximum ports per range (default: 100, max: 65535)')
    ap.add_argument('--tcp-timeout', type=float, default=1.0, metavar='SEC',
                    help='TCP connection timeout in seconds (default: 1.0)')
    ap.add_argument('--force', action='store_true',
                    help='Force large ranges without confirmation prompts')
    ap.add_argument('--dscp', type=int, metavar='VALUE',
                    help='DSCP value for packet marking (32-63). Required for coordination. '
                         'Falls back to KSMS_JOB_DSCP environment variable if not specified.')
    ap.add_argument('-j', '--json', action='store_true',
                    help='Output results in JSON format')
    ap.add_argument('-v', '--verbose', action='count', default=0,
                    help='Increase verbosity (-v, -vv, -vvv)')
    args = ap.parse_args()
    
    # Set global verbosity level
    VERBOSE = args.verbose

    # Validate range-limit parameter
    if args.range_limit < 1 or args.range_limit > 65535:
        print("Error: --range-limit must be between 1 and 65535", file=sys.stderr)
        sys.exit(1)

    # Initialize TsimRegistryManager for coordination
    try:
        import json

        # Get config path: TSIM_CONFIG_PATH env var or default
        config_path = os.environ.get('TSIM_CONFIG_PATH', '/opt/tsim/wsgi/conf/config.json')

        # Try to load config
        config = None
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            if VERBOSE >= 3:
                _dbg(f"[DEBUG] Loaded config from: {config_path}", 3)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            # If TSIM_CONFIG_PATH was explicitly set but invalid, try default
            if 'TSIM_CONFIG_PATH' in os.environ:
                if VERBOSE >= 1:
                    _dbg(f"[WARN] Invalid config at TSIM_CONFIG_PATH={config_path}: {e}", 1)
                try:
                    with open('/opt/tsim/wsgi/conf/config.json', 'r') as f:
                        config = json.load(f)
                    if VERBOSE >= 3:
                        _dbg("[DEBUG] Loaded config from default location", 3)
                except Exception:
                    pass

        if not config:
            _dbg(
                f"[WARN] Cannot load config.json from {config_path}. "
                "Set TSIM_CONFIG_PATH environment variable. "
                "Continuing without registry coordination.", 1
            )
            REGISTRY_MGR = None
        else:
            # Initialize TsimRegistryManager with loaded config
            # All paths (data_dir, lock_dir, registry_files) come from config.json
            from tsim.core.registry_manager import TsimRegistryManager
            import logging
            logger = logging.getLogger(__name__)
            if VERBOSE >= 3:
                logger.setLevel(logging.DEBUG)
            elif VERBOSE >= 2:
                logger.setLevel(logging.INFO)
            else:
                logger.setLevel(logging.WARNING)

            REGISTRY_MGR = TsimRegistryManager(config, logger)
            if VERBOSE >= 2:
                _dbg("[INFO] TsimRegistryManager initialized for coordination", 2)

    except Exception as e:
        _dbg(f"[WARN] Failed to initialize TsimRegistryManager: {e}", 1)
        if VERBOSE >= 3:
            import traceback
            _dbg(f"[DEBUG] Traceback: {traceback.format_exc()}", 3)
        REGISTRY_MGR = None

    bridges, hosts = load_registries()
    ip_map = build_ip_to_namespaces(bridges, hosts)

    # Resolve all source namespaces (hosts) owning the IP
    src_namespaces = ip_map.get(args.source, [])
    if not src_namespaces:
        print(f"Error: Source IP {args.source} not found in registries", file=sys.stderr)
        sys.exit(1)
    
    if VERBOSE >= 1:
        print(f"[INFO] Source IP {args.source} found in namespace(s): {', '.join(src_namespaces)}", file=sys.stderr)
    _dbg(f"[DEBUG] Source namespaces for {args.source}: {src_namespaces}", 2)

    # Infer routers involved
    routers = infer_routers_for_source(args.source, bridges, hosts, ip_map)
    if not routers:
        print(f"Error: No routers inferred for source {args.source}", file=sys.stderr)
        sys.exit(1)
    
    if VERBOSE >= 1:
        print(f"[INFO] Testing through router(s): {', '.join(routers)}", file=sys.stderr)
    _dbg(f"[DEBUG] Routers to test: {routers}", 2)

    # Parse services
    try:
        services = parse_ports(args.ports, args.default_proto, args.max_services, args.range_limit, args.force)
        
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    if VERBOSE >= 1:
        svc_str = ', '.join([f"{p}/{pr}" for p, pr in services])
        print(f"[INFO] Testing {len(services)} service(s): {svc_str}", file=sys.stderr)
    _dbg(f"[DEBUG] Services: {services}", 2)

    # Generate unique run ID for this job
    run_id = f"KSMS{os.getpid()}_{int(time.time() * 1000) % 100000}"

    # Get DSCP value: CLI argument first, then environment variable, then default to 32
    if args.dscp is not None:
        job_dscp = args.dscp
    else:
        job_dscp = int(os.environ.get('KSMS_JOB_DSCP', '32'))

    # Validate DSCP range (use reserved range 32-63 for KSMS)
    if not (32 <= job_dscp <= 63):
        raise ValueError(f"Invalid DSCP value {job_dscp} (must be 32-63, 0x20-0x3F)")
    
    # Assign single DSCP value to all services in this job
    svc_tokens: Dict[Tuple[int,str], Dict] = {}
    for port, proto in services:
        # All services in this job use the same DSCP value
        svc_tokens[(port, proto)] = {'dscp': job_dscp, 'tos': job_dscp << 2}
        
        if VERBOSE >= 3:
            _dbg(f"  Service {port}/{proto}: DSCP={job_dscp} (0x{job_dscp:02x}), TOS={job_dscp << 2}", 3)
    
    if VERBOSE >= 2:
        _dbg(f"[INFO] Job {run_id}: Using DSCP={job_dscp} for all {len(services)} services", 2)
    
    if VERBOSE >= 1:
        _dbg(f"[INFO] Using run ID: {run_id}", 1)

    # COORDINATION: Wait for routers if locked by detailed jobs (quick jobs wait)
    if REGISTRY_MGR:
        if VERBOSE >= 2:
            print(f"\n[COORDINATION] Checking router availability...", file=sys.stderr)

        for router in routers:
            if VERBOSE >= 3:
                _dbg(f"  Checking if router {router} is locked...", 3)

            # Wait for router to be free (inotify-based, no polling)
            if not REGISTRY_MGR.wait_for_router(router, timeout=30.0):
                print(f"Error: Router {router} locked by detailed job, timeout waiting", file=sys.stderr)
                sys.exit(1)

            if VERBOSE >= 3:
                _dbg(f"  Router {router} is free, proceeding", 3)

        if VERBOSE >= 2:
            print(f"  All routers available, proceeding with test", file=sys.stderr)

    # COORDINATION: Acquire source host leases
    acquired_leases = []
    if REGISTRY_MGR:
        if VERBOSE >= 2:
            print(f"[COORDINATION] Acquiring source host leases...", file=sys.stderr)

        for src_host in src_namespaces:
            # Find which router this host is connected to
            host_router = None
            for host_name, host_info in hosts.items():
                if host_name == src_host:
                    host_router = host_info.get('connected_to')
                    break

            if not host_router:
                if VERBOSE >= 2:
                    _dbg(f"  WARNING: Could not determine router for source host {src_host}, skipping lease", 2)
                continue

            try:
                ref_count = REGISTRY_MGR.acquire_source_host_lease(
                    run_id=run_id,
                    host_name=src_host,
                    job_type='quick',
                    router_name=host_router,
                    dscp=job_dscp
                )
                acquired_leases.append(src_host)

                if VERBOSE >= 3:
                    _dbg(f"  Acquired lease for {src_host}: ref_count={ref_count}", 3)

            except Exception as e:
                _dbg(f"  WARNING: Failed to acquire lease for {src_host}: {e}", 1)

        if VERBOSE >= 2:
            print(f"  Acquired {len(acquired_leases)} source host lease(s)", file=sys.stderr)

    if VERBOSE >= 1:
        print(f"\n[PHASE 1] Preparing routers for testing...", file=sys.stderr)

    # Per-router preparation in parallel
    router_results: Dict[str, Dict] = {r: {'egress': None, 'nexthop': None, 'before': '', 'after': ''} for r in routers}

    def prepare_router(rname: str):
        if VERBOSE >= 2:
            print(f"  [{rname}] Preparing router...", file=sys.stderr)
        
        # Determine egress iface and next hop via ip route get
        iface, nexthop = egress_iface_and_nexthop_for(rname, args.destination)
        router_results[rname]['egress'] = iface
        router_results[rname]['nexthop'] = nexthop
        
        if VERBOSE >= 2:
            print(f"  [{rname}] Route to {args.destination}: via {nexthop or 'direct'} dev {iface or 'unknown'}", file=sys.stderr)
        _dbg(f"  [{rname}] DEBUG: egress iface = {iface}, nexthop = {nexthop}", 3)
        # Cleanup: Remove ALL old TSIM_KSMS rules using individual iptables commands
        snap = iptables_save_mangle(rname, with_counters=False)
        cleanup_commands = []
        removed = 0

        # Build iptables -D commands for each old TSIM_KSMS rule
        for line in snap.splitlines():
            if 'TSIM_KSMS=' in line and line.startswith('-A '):
                # Convert from iptables-save format (-A CHAIN ...) to delete format
                # -A PREROUTING -p tcp ... → iptables -t mangle -D PREROUTING -p tcp ...
                rule_spec = line[3:]  # Remove "-A "
                cleanup_commands.append(f"iptables -t mangle -D {rule_spec}")
                removed += 1

        # Also remove TSIM_TAP_FW chain if it exists
        cleanup_commands.append("iptables -t mangle -F TSIM_TAP_FW || true")
        cleanup_commands.append("iptables -t mangle -X TSIM_TAP_FW || true")

        if removed > 0:
            result = execute_iptables_script(rname, cleanup_commands)
            if result.returncode == 0:
                if VERBOSE >= 2:
                    print(f"  [{rname}] Cleaned {removed} stale TSIM_KSMS rule(s)", file=sys.stderr)
            else:
                _dbg(f"  [{rname}] WARNING: Failed to clean old rules: {result.stderr}", 1)
        # Insert taps using individual iptables commands
        insert_commands = []

        # Create TSIM_TAP_FW chain
        insert_commands.append("iptables -t mangle -N TSIM_TAP_FW || true")
        insert_commands.append("iptables -t mangle -F TSIM_TAP_FW")
        insert_commands.append("iptables -t mangle -A TSIM_TAP_FW -j RETURN")

        # Add a catch-all rule to verify packets are traversing at all (for debugging)
        if VERBOSE >= 3:
            comment_debug = f'TSIM_KSMS={run_id}:DEBUG:CATCH_ALL'
            insert_commands.append(f"iptables -t mangle -I PREROUTING 1 -d {args.destination} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_debug)}")

        # Insert rules for each service (use -I to insert at beginning)
        for port, proto in services:
            dscp = svc_tokens[(port, proto)]['dscp']
            comment_pre = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
            comment_post = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"

            # PREROUTING rule
            insert_commands.append(
                f"iptables -t mangle -I PREROUTING 1 -p {proto} -m dscp --dscp 0x{dscp:02x} "
                f"-m {proto} --dport {port} -m comment --comment {shlex.quote(comment_pre)} -j TSIM_TAP_FW"
            )

            # POSTROUTING rule
            insert_commands.append(
                f"iptables -t mangle -I POSTROUTING 1 -p {proto} -m dscp --dscp 0x{dscp:02x} "
                f"-m {proto} --dport {port} -m comment --comment {shlex.quote(comment_post)} -j TSIM_TAP_FW"
            )

            if VERBOSE >= 3:
                _dbg(f"  [{rname}] DEBUG: Will insert rule for {port}/{proto} with DSCP={dscp}", 3)

        # Execute all iptables commands
        if VERBOSE >= 2:
            print(f"  [{rname}] Inserting iptables taps...", file=sys.stderr)

        try:
            result = execute_iptables_script(rname, insert_commands)

            if VERBOSE >= 2:
                print(f"  [{rname}] iptables script completed with code {result.returncode}", file=sys.stderr)

            if VERBOSE >= 3:
                _dbg(f"  [{rname}] DEBUG: iptables script returned code {result.returncode}", 3)
                if result.stdout:
                    _dbg(f"  [{rname}] DEBUG: stdout: {result.stdout[:500]}", 3)
                if result.stderr:
                    _dbg(f"  [{rname}] DEBUG: stderr: {result.stderr[:500]}", 3)

            if result.returncode == 0:
                if VERBOSE >= 2:
                    print(f"  [{rname}] Inserted iptables taps for {len(services)} service(s)", file=sys.stderr)

                # Verify rules were actually inserted
                if VERBOSE >= 3:
                    verify = iptables_save_mangle(rname, with_counters=False)
                    ksms_count = sum(1 for line in verify.splitlines() if 'TSIM_KSMS' in line)
                    _dbg(f"  [{rname}] DEBUG: Verification shows {ksms_count} TSIM_KSMS rules now present", 3)
            else:
                if VERBOSE >= 2:
                    print(f"  [{rname}] FAILED to insert iptables taps (code {result.returncode})", file=sys.stderr)
                    if result.stderr:
                        print(f"  [{rname}] Error: {result.stderr.strip()}", file=sys.stderr)
                _dbg(f"  [{rname}] DEBUG: iptables script failed with code {result.returncode}", 3)
        except Exception as e:
            if VERBOSE >= 1:
                print(f"  [{rname}] ERROR running iptables script: {e}", file=sys.stderr)
                import traceback
                if VERBOSE >= 3:
                    _dbg(f"  [{rname}] DEBUG: Full traceback:\n{traceback.format_exc()}", 3)
            _dbg(f"  [{rname}] DEBUG: Exception during iptables script: {e}", 2)
        # Baseline snapshot
        router_results[rname]['before'] = iptables_save_mangle(rname)
        
        if VERBOSE >= 3:
            print(f"  [{rname}] Captured baseline counter snapshot", file=sys.stderr)
            # Check if our rules are in the snapshot
            snapshot_lines = router_results[rname]['before'].splitlines()
            ksms_rules = [l for l in snapshot_lines if 'TSIM_KSMS' in l]
            _dbg(f"  [{rname}] DEBUG: Found {len(ksms_rules)} TSIM_KSMS rules in baseline snapshot", 3)
            # Show ALL our rules to verify they match what we expect
            for rule in ksms_rules:
                if run_id in rule:  # Only show rules from this run
                    _dbg(f"  [{rname}] DEBUG: Our rule: {rule}", 3)
        # Configure static neighbor for next hop (not destination!)
        if iface and nexthop:
            result = run(['ip', 'netns', 'exec', rname, 'ip', 'neigh', 'replace', nexthop, 'lladdr', '02:00:00:00:02:00', 'dev', iface, 'nud', 'permanent'])
            if VERBOSE >= 2:
                if result.returncode == 0:
                    print(f"  [{rname}] Configured static ARP entry for next hop {nexthop} on {iface}", file=sys.stderr)
                else:
                    print(f"  [{rname}] FAILED to configure ARP entry for {nexthop} (code {result.returncode})", file=sys.stderr)
            _dbg(f"  [{rname}] DEBUG: neighbor replace result = {result.returncode}", 3)
        else:
            if VERBOSE >= 2:
                print(f"  [{rname}] Skipping ARP config (no egress interface or nexthop found)", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(prepare_router, r) for r in routers]
        for _ in as_completed(futs):
            pass
    
    if VERBOSE >= 1:
        print(f"[PHASE 1] Router preparation completed\n", file=sys.stderr)

    # Map each router to a best source namespace (a host with this IP connected to that router)
    router_src_ns: Dict[str, Optional[str]] = {r: None for r in routers}
    for ns in src_namespaces:
        if ns in hosts:
            r = hosts.get(ns, {}).get('connected_to')
            if r in router_src_ns and router_src_ns[r] is None:
                router_src_ns[r] = ns
    
    if VERBOSE >= 2:
        print(f"[INFO] Per-router source namespaces: {router_src_ns}", file=sys.stderr)
    _dbg(f"[DEBUG] Per-router source namespaces: {router_src_ns}", 3)
    if VERBOSE >= 1:
        print(f"[PHASE 2] Emitting test probes...", file=sys.stderr)
    
    # Debug: verify our rules are still present before emitting
    if VERBOSE >= 3:
        for rname in routers:
            check_save = iptables_save_mangle(rname)
            our_rules = [l for l in check_save.splitlines() if f'KSMS={run_id}' in l]
            _dbg(f"  [{rname}] DEBUG: Pre-emission check: found {len(our_rules)} rules with our run ID", 3)
            if len(our_rules) == 0:
                _dbg(f"  [{rname}] WARNING: Our rules have disappeared before emission!", 1)
    
    # Emit probes per router using its associated source namespace (if available)
    def emit_for_router(rname: str):
        ns = router_src_ns.get(rname)
        if not ns:
            if VERBOSE >= 2:
                print(f"  [{rname}] No source namespace available, skipping probe emission", file=sys.stderr)
            return
        
        if VERBOSE >= 2:
            print(f"  [{rname}] Emitting probes from namespace {ns}", file=sys.stderr)
        
        result = emit_probes_in_source_ns(ns, args.destination, services, svc_tokens, args.tcp_timeout)
        
        if VERBOSE >= 2:
            if result == 0:
                print(f"  [{rname}] Probe emission completed successfully", file=sys.stderr)
            else:
                print(f"  [{rname}] Probe emission had issues (code {result})", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(emit_for_router, r) for r in routers]
        for _ in as_completed(futs):
            pass
    
    if VERBOSE >= 1:
        print(f"[PHASE 2] Probe emission completed\n", file=sys.stderr)

    if VERBOSE >= 1:
        print(f"[PHASE 3] Collecting results...", file=sys.stderr)
    
    # Debug: check if our rules are still there after probe emission
    if VERBOSE >= 3:
        _dbg("[DEBUG] Checking if our rules survived probe emission:", 3)
        for rname in routers:
            check_save = iptables_save_mangle(rname)
            our_rules = [l for l in check_save.splitlines() if f'KSMS={run_id}' in l]
            _dbg(f"  [{rname}] Post-emission check: found {len(our_rules)} rules with our run ID", 3)
            if len(our_rules) == 0:
                _dbg(f"  [{rname}] ERROR: Our rules disappeared after probe emission!", 1)
                # Show what rules ARE there
                any_ksms = [l for l in check_save.splitlines() if 'TSIM_KSMS=' in l]
                if any_ksms:
                    _dbg(f"  [{rname}] Found {len(any_ksms)} TSIM_KSMS rules (from other runs)", 2)
    
    # Final snapshots and cleanup in parallel
    def finalize_router(rname: str):
        if VERBOSE >= 2:
            print(f"  [{rname}] Taking final counter snapshot...", file=sys.stderr)
        
        # Final snapshot only; do not remove taps or neighbors here (pre-run reconcile handles stale state)
        router_results[rname]['after'] = iptables_save_mangle(rname)
        
        if VERBOSE >= 3:
            print(f"  [{rname}] Final snapshot captured", file=sys.stderr)
        _dbg(f"  [{rname}] DEBUG: Final snapshot captured", 3)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(finalize_router, r) for r in routers]
        for _ in as_completed(futs):
            pass
    
    if VERBOSE >= 1:
        print(f"[PHASE 3] Result collection completed\n", file=sys.stderr)
        print(f"[PHASE 4] Analyzing counter deltas...\n", file=sys.stderr)

    # Build results
    results = []
    for r in routers:
        rres = {'name': r, 'iface': router_results[r]['egress'], 'services': []}
        before = router_results[r]['before']
        after = router_results[r]['after']
        
        # Debug: show what rules we have in the snapshots
        if VERBOSE >= 3:
            _dbg(f"\n  [{r}] DEBUG: Analyzing snapshots for run_id={run_id}", 3)
            before_ksms = [l for l in before.splitlines() if 'TSIM_KSMS' in l]
            after_ksms = [l for l in after.splitlines() if 'TSIM_KSMS' in l]
            _dbg(f"  [{r}] DEBUG: Before snapshot has {len(before_ksms)} TSIM_KSMS rules", 3)
            _dbg(f"  [{r}] DEBUG: After snapshot has {len(after_ksms)} TSIM_KSMS rules", 3)
            if after_ksms and VERBOSE >= 3:
                _dbg(f"  [{r}] DEBUG: Sample rules from after snapshot:", 3)
                for rule in after_ksms[:5]:  # Show first 5 rules
                    _dbg(f"  [{r}] DEBUG:   {rule[:150]}", 3)
            
            # Check the catch-all rule to see if ANY packets traversed
            catch_all_comment = f"TSIM_KSMS={run_id}:DEBUG:CATCH_ALL"
            cb_pkts, _ = extract_counter(before, catch_all_comment)
            ca_pkts, _ = extract_counter(after, catch_all_comment)
            catch_all_delta = ca_pkts - cb_pkts
            if catch_all_delta > 0:
                _dbg(f"  [{r}] DEBUG: CATCH_ALL rule matched {catch_all_delta} packets!", 3)
            else:
                _dbg(f"  [{r}] DEBUG: CATCH_ALL rule matched 0 packets - no packets to {args.destination} seen", 3)
        
        for port, proto in services:
            d = svc_tokens[(port, proto)]
            dscp_val = d['dscp']
            tos_val = d['tos']
            pre_c = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
            post_c = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"
            
            if VERBOSE >= 3:
                _dbg(f"  [{r}] DEBUG: Service {port}/{proto}: DSCP={dscp_val} TOS={tos_val}", 3)
                _dbg(f"  [{r}] DEBUG: Looking for PREROUTING comment: {pre_c}", 3)
            b_pkts, _ = extract_counter(before, pre_c)
            a_pkts, _ = extract_counter(after, pre_c)
            
            if VERBOSE >= 3:
                _dbg(f"  [{r}] DEBUG: Looking for POSTROUTING comment: {post_c}", 3)
            b2_pkts, _ = extract_counter(before, post_c)
            a2_pkts, _ = extract_counter(after, post_c)
            
            pre_delta = a_pkts - b_pkts
            post_delta = a2_pkts - b2_pkts
            if post_delta > 0:
                verdict = 'YES'
            elif pre_delta > 0 and post_delta == 0:
                verdict = 'NO'
            else:
                verdict = 'UNKNOWN'
            
            if VERBOSE >= 2:
                print(f"  [{r}] {port:5}/{proto:3} : PREROUTING={pre_delta:3} POSTROUTING={post_delta:3} => {verdict}", file=sys.stderr)
            _dbg(f"  [{r}] DEBUG: {port}/{proto}: pre {pre_delta} post {post_delta} -> {verdict}", 3)
            
            rres['services'].append({'port': port, 'protocol': proto, 'result': verdict})
        results.append(rres)
    
    if VERBOSE >= 1:
        print(f"\n[COMPLETE] Analysis finished\n", file=sys.stderr)

    # CLEANUP: Remove our test rules to prevent accumulation
    if VERBOSE >= 2:
        print(f"[CLEANUP] Removing test rules...", file=sys.stderr)
    
    def cleanup_router(rname: str):
        # Remove static ARP entry that was configured during setup
        if rname in router_results:
            nexthop = router_results[rname].get('nexthop')
            iface = router_results[rname].get('egress')
            if nexthop and iface:
                # Remove the static ARP entry we added
                result = run(['ip', 'netns', 'exec', rname, 'ip', 'neigh', 'del', nexthop, 'dev', iface])
                if VERBOSE >= 2:
                    if result.returncode == 0:
                        print(f"  [{rname}] Removed static ARP entry for {nexthop} on {iface}", file=sys.stderr)
                    else:
                        # Only warn if it's not just "no such entry" (which is fine)
                        stderr_msg = result.stderr.strip() if result.stderr else ""
                        if "No such file or directory" not in stderr_msg and "Cannot assign requested address" not in stderr_msg:
                            if VERBOSE >= 1:
                                print(f"  [{rname}] ARP cleanup warning: {stderr_msg}", file=sys.stderr)
        
        # Remove all our TSIM_KSMS rules with our run_id using individual iptables commands
        snap = iptables_save_mangle(rname, with_counters=False)
        cleanup_commands = []
        removed = 0
        has_other_tsim_rules = False

        # Build iptables -D commands for each rule from this run
        for line in snap.splitlines():
            # Remove only OUR rules from this run
            if f'TSIM_KSMS={run_id}' in line and line.startswith('-A '):
                # Convert from iptables-save format to delete format
                rule_spec = line[3:]  # Remove "-A "
                cleanup_commands.append(f"iptables -t mangle -D {rule_spec}")
                removed += 1
            # Check if there are other TSIM_KSMS rules from other runs
            elif 'TSIM_KSMS=' in line and line.startswith('-A '):
                has_other_tsim_rules = True

        # If no other TSIM_KSMS rules remain, also remove the TSIM_TAP_FW chain
        if not has_other_tsim_rules:
            cleanup_commands.append("iptables -t mangle -F TSIM_TAP_FW || true")
            cleanup_commands.append("iptables -t mangle -X TSIM_TAP_FW || true")

        if removed > 0:
            result = execute_iptables_script(rname, cleanup_commands)
            if result.returncode == 0:
                if VERBOSE >= 3:
                    _dbg(f"  [{rname}] Removed {removed} test rules", 3)
            else:
                _dbg(f"  [{rname}] WARNING: Failed to cleanup iptables rules: {result.stderr}", 1)
    
    # Cleanup in parallel
    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(cleanup_router, r) for r in routers]
        for _ in as_completed(futs):
            pass

    # COORDINATION: Release source host leases
    if REGISTRY_MGR and acquired_leases:
        if VERBOSE >= 2:
            print(f"[COORDINATION] Releasing source host leases...", file=sys.stderr)

        for src_host in acquired_leases:
            try:
                ref_count, should_delete = REGISTRY_MGR.release_source_host_lease(
                    run_id=run_id,
                    host_name=src_host
                )

                if VERBOSE >= 3:
                    _dbg(f"  Released lease for {src_host}: ref_count={ref_count}, should_delete={should_delete}", 3)

                # Quick jobs never delete physical hosts - they're managed by host_namespace_setup
                # Just release the lease and let ref counting handle persistence

            except Exception as e:
                _dbg(f"  WARNING: Failed to release lease for {src_host}: {e}", 1)

        if VERBOSE >= 2:
            print(f"  Released {len(acquired_leases)} source host lease(s)", file=sys.stderr)

    if VERBOSE >= 2:
        print(f"[CLEANUP] Completed\n", file=sys.stderr)

    if args.json:
        print(json.dumps({'source': args.source, 'destination': args.destination, 'routers': results}, indent=2))
    else:
        # Different output based on verbosity
        if VERBOSE == 0:
            # Compact output
            print(f"ksms: {args.source} -> {args.destination}")
            svc_str = ', '.join([f"{p}/{pr}" for p, pr in services])
            print(f"services: {svc_str}")
            for r in results:
                print(f"\nRouter {r['name']} [{r.get('iface') or '?'}]")
                for s in r['services']:
                    print(f"  {s['port']}/{s['protocol']}: {s['result']}")
        elif VERBOSE >= 1:
            # Verbose output with clear sections
            print(f"=== KSMS Test Results ===")
            print(f"Source: {args.source}")
            print(f"Destination: {args.destination}")
            print(f"Services tested: {', '.join([f'{p}/{pr}' for p, pr in services])}")
            print()
            
            for r in results:
                iface_info = f" via {r.get('iface')}" if r.get('iface') else " (no egress interface)"
                print(f"Router: {r['name']}{iface_info}")
                print("-" * 40)
                
                # Count results
                yes_count = sum(1 for s in r['services'] if s['result'] == 'YES')
                no_count = sum(1 for s in r['services'] if s['result'] == 'NO')
                unknown_count = sum(1 for s in r['services'] if s['result'] == 'UNKNOWN')
                
                for s in r['services']:
                    status_symbol = '✓' if s['result'] == 'YES' else ('✗' if s['result'] == 'NO' else '?')
                    print(f"  [{status_symbol}] {s['port']:5}/{s['protocol']:<3} : {s['result']}")
                
                # Summary per router
                total = len(r['services'])
                if yes_count == total:
                    print(f"  [SUCCESS] All {total} services are reachable")
                elif no_count == total:
                    print(f"  [BLOCKED] All {total} services are blocked")
                elif unknown_count == total:
                    print(f"  [ERROR] Could not test any services")
                else:
                    print(f"  [MIXED] YES: {yes_count}, NO: {no_count}, UNKNOWN: {unknown_count}")
                print()

    # Exit with non-zero if any UNKNOWN (optional policy), else 0
    sys.exit(0)


if __name__ == '__main__':
    main()

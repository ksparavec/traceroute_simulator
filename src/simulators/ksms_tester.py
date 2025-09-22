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
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from tsim.core.config_loader import get_registry_paths

# Verbosity placeholder (kept for CLI parity)
VERBOSE = 0

def _dbg(msg: str, level: int = 1):
    # Intentionally no-op to avoid heavy logging during shell startup
    return


def _sudo_wrap(cmd: List[str]) -> List[str]:
    return (['sudo', '-n'] + cmd) if os.geteuid() != 0 else cmd


def run(cmd: List[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
    return subprocess.run(_sudo_wrap(cmd), input=input_data.encode() if input_data else None,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)


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


def parse_ports(port_spec: str, default_proto: str, max_services: int) -> List[Tuple[int, str]]:
    """Parse port spec using the same logic as WSGI TsimPortParserService.
    Import the service by adding the wsgi dir to sys.path to avoid requiring 'wsgi' as a package.
    """
    try:
        # Project root = .../src/.. (two levels up from this file)
        project_root = Path(__file__).resolve().parents[2]
        wsgi_dir = project_root / 'wsgi'
        if str(wsgi_dir) not in sys.path:
            sys.path.insert(0, str(wsgi_dir))
        from services.tsim_port_parser_service import TsimPortParserService  # type: ignore
        parser = TsimPortParserService()
        return parser.parse_port_spec(port_spec, default_proto, max_services)
    except Exception as e:
        # Fallback: basic parser for simple comma-separated list of port[/proto]
        _dbg(f"[WARN] Falling back to basic port parser: {e}", 1)
        result: List[Tuple[int, str]] = []
        for part in [p.strip() for p in port_spec.split(',') if p.strip()]:
            if '/' in part:
                p_str, pr = part.split('/', 1)
                p = int(p_str)
                pr = pr.lower()
            else:
                p = int(part)
                pr = default_proto
            result.append((p, pr))
        if len(result) > max_services:
            result = result[:max_services]
        return result


def egress_iface_for(router: str, dst_ip: str) -> Optional[str]:
    # ip netns exec router ip route get <dst>
    cp = run(['ip', 'netns', 'exec', router, 'ip', 'route', 'get', dst_ip])
    if cp.returncode != 0:
        return None
    m = re.search(r'\bdev\s+(\S+)', cp.stdout.splitlines()[0])
    return m.group(1) if m else None


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


def build_insert_payload_from_existing(existing_save: str, insert_lines: List[str]) -> str:
    """Take iptables-save output for mangle table and append our -I lines before COMMIT."""
    lines = existing_save.splitlines()
    out: List[str] = []
    committed = False
    for ln in lines:
        if ln.strip() == 'COMMIT' and not committed:
            # Insert our lines just before COMMIT
            for ins in insert_lines:
                out.append(ins)
            out.append('COMMIT')
            committed = True
        else:
            out.append(ln)
    # If COMMIT not found (unexpected), create minimal table
    if not committed:
        out = ['*mangle', ':PREROUTING ACCEPT [0:0]', ':INPUT ACCEPT [0:0]', ':FORWARD ACCEPT [0:0]', ':OUTPUT ACCEPT [0:0]', ':POSTROUTING ACCEPT [0:0]'] + insert_lines + ['COMMIT']
    # Ensure TSIM_TAP_FW exists and returns
    # If not present, add declaration and RETURN rule near top
    if ':TSIM_TAP_FW ' not in existing_save:
        # Rebuild with TSIM_TAP_FW
        rebuilt: List[str] = []
        inserted_decl = False
        for ln in out:
            if not inserted_decl and ln.startswith(':PREROUTING'):
                rebuilt.append(':TSIM_TAP_FW - [0:0]')
                inserted_decl = True
            rebuilt.append(ln)
        out = []
        inserted_return = False
        # Add RETURN rule early (after *mangle header if present)
        for ln in rebuilt:
            out.append(ln)
            if not inserted_return and ln.startswith('*mangle'):
                out.append('-F TSIM_TAP_FW')
                out.append('-A TSIM_TAP_FW -j RETURN')
                inserted_return = True
    return '\n'.join(out) + ('\n' if not out or not out[-1].endswith('\n') else '')


def extract_counter(snapshot: str, comment: str) -> Tuple[int, int]:
    # Lines look like: -A PREROUTING -c <pkts> <bytes> ... -m comment --comment TSIM_KSMS=...
    pkts = bytes_ = 0
    for line in snapshot.splitlines():
        if comment in line:
            m = re.search(r'-c\s+(\d+)\s+(\d+)', line)
            if m:
                pkts = int(m.group(1)); bytes_ = int(m.group(2))
            break
    return pkts, bytes_


def emit_probes_in_source_ns(source_ns: str, dst_ip: str, services: List[Tuple[int, str]], svc_tokens: Dict[Tuple[int, str], Dict], tcp_timeout: float) -> int:
    # Build a small python helper which sends all probes
    helper = r"""
import socket, sys, json, time
dst_ip = sys.argv[1]
tcp_timeout = float(sys.argv[2])
spec = json.loads(sys.argv[3])  # list of {port,proto,tos}

def send_tcp(port, tos):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
        s.settimeout(tcp_timeout)
        try:
            s.connect((dst_ip, port))
        except Exception:
            pass
        s.close()
    except Exception:
        pass

def send_udp(port, tos):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
        s.sendto(b"x", (dst_ip, port))
        s.close()
    except Exception:
        pass

for item in spec:
    port = int(item['port']); proto = item['proto']; tos = int(item['tos'])
    if proto == 'tcp':
        send_tcp(port, tos)
    else:
        send_udp(port, tos)
"""
    spec = [ {'port': p, 'proto': pr, 'tos': svc_tokens[(p,pr)]['tos']} for (p,pr) in services ]
    argv = ['ip', 'netns', 'exec', source_ns, sys.executable, '-c', helper, dst_ip, str(tcp_timeout), json.dumps(spec)]
    cp = run(argv)
    return cp.returncode


def main():
    ap = argparse.ArgumentParser(description='KSMS Tester backend')
    ap.add_argument('--source', required=True)
    ap.add_argument('--destination', required=True)
    ap.add_argument('--ports', required=True)
    ap.add_argument('--default-proto', choices=['tcp','udp'], default='tcp')
    ap.add_argument('--max-services', type=int, default=10)
    ap.add_argument('--tcp-timeout', type=float, default=1.0)
    ap.add_argument('-j', '--json', action='store_true')
    ap.add_argument('-v', '--verbose', action='count', default=0)
    args = ap.parse_args()

    bridges, hosts = load_registries()
    ip_map = build_ip_to_namespaces(bridges, hosts)

    # Resolve all source namespaces (hosts) owning the IP
    src_namespaces = ip_map.get(args.source, [])
    if not src_namespaces:
        print(f"Error: Source IP {args.source} not found in registries", file=sys.stderr)
        sys.exit(1)
    _dbg(f"Source namespaces for {args.source}: {src_namespaces}", 1)

    # Infer routers involved
    routers = infer_routers_for_source(args.source, bridges, hosts, ip_map)
    if not routers:
        print(f"Error: No routers inferred for source {args.source}", file=sys.stderr)
        sys.exit(1)
    _dbg(f"Routers to test: {routers}", 1)

    # Parse services
    try:
        services = parse_ports(args.ports, args.default_proto, args.max_services)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    _dbg(f"Services: {services}", 1)

    # Assign DSCP/TOS per service
    svc_tokens: Dict[Tuple[int,str], Dict] = {}
    for idx, (port, proto) in enumerate(services):
        dscp = 0x20 + idx
        svc_tokens[(port, proto)] = {'dscp': dscp, 'tos': dscp << 2}

    run_id = f"KSMS{os.getpid()}"

    # Per-router preparation in parallel
    router_results: Dict[str, Dict] = {r: {'egress': None, 'before': '', 'after': ''} for r in routers}

    def prepare_router(rname: str):
        # Determine egress iface via ip route get
        iface = egress_iface_for(rname, args.destination)
        router_results[rname]['egress'] = iface
        _dbg(f"[{rname}] egress iface for {args.destination}: {iface or '?'}", 1)
        # Reconcile: remove any stale TSIM_KSMS rules from previous runs
        snap = iptables_save_mangle(rname)
        dels: List[str] = []
        for line in snap.splitlines():
            if 'TSIM_KSMS=' in line and line.startswith('-A '):
                # Transform -A CHAIN ... --comment XYZ -> -D CHAIN ... --comment XYZ
                dels.append(line.replace('-A ', '-D ', 1))
        if dels:
            payload = "*mangle\n" + "\n".join(dels) + "\nCOMMIT\n"
            run(['ip', 'netns', 'exec', rname, 'iptables-restore', '-c'], input_data=payload)
            _dbg(f"[{rname}] Reconciled {len(dels)} stale TSIM_KSMS rules", 2)
        # Insert taps (build from existing save to satisfy iptables-restore format)
        existing = iptables_save_mangle(rname, with_counters=False)
        insert_lines = []
        # Ensure TSIM_TAP_FW RETURN is present via build function
        for port, proto in services:
            dscp = svc_tokens[(port, proto)]['dscp']
            comment_pre = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
            comment_post = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"
            insert_lines.append(f"-I PREROUTING 1 -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_pre)}")
            insert_lines.append(f"-I POSTROUTING 1 -m dscp --dscp {dscp} -p {proto} --dport {port} -j TSIM_TAP_FW -m comment --comment {shlex.quote(comment_post)}")
        payload = build_insert_payload_from_existing(existing, insert_lines)
        run(['ip', 'netns', 'exec', rname, 'iptables-restore', '-c'], input_data=payload)
        _dbg(f"[{rname}] Inserted taps for {len(services)} services", 2)
        # Baseline snapshot
        router_results[rname]['before'] = iptables_save_mangle(rname)
        if VERBOSE >= 3:
            _dbg(f"[{rname}] Baseline snapshot captured", 3)
        # Configure static neighbor if iface available
        if iface:
            run(['ip', 'netns', 'exec', rname, 'ip', 'neigh', 'replace', args.destination, 'lladdr', '02:00:00:00:02:00', 'dev', iface, 'nud', 'permanent'])
            _dbg(f"[{rname}] Static neighbor set for {args.destination} on {iface}", 2)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(prepare_router, r) for r in routers]
        for _ in as_completed(futs):
            pass

    # Map each router to a best source namespace (a host with this IP connected to that router)
    router_src_ns: Dict[str, Optional[str]] = {r: None for r in routers}
    for ns in src_namespaces:
        if ns in hosts:
            r = hosts.get(ns, {}).get('connected_to')
            if r in router_src_ns and router_src_ns[r] is None:
                router_src_ns[r] = ns
    _dbg(f"Per-router source namespaces: {router_src_ns}", 1)
    # Emit probes per router using its associated source namespace (if available)
    def emit_for_router(rname: str):
        ns = router_src_ns.get(rname)
        if not ns:
            return
        emit_probes_in_source_ns(ns, args.destination, services, svc_tokens, args.tcp_timeout)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(emit_for_router, r) for r in routers]
        for _ in as_completed(futs):
            pass

    # Final snapshots and cleanup in parallel
    def finalize_router(rname: str):
        # Final snapshot only; do not remove taps or neighbors here (pre-run reconcile handles stale state)
        router_results[rname]['after'] = iptables_save_mangle(rname)
        if VERBOSE >= 3:
            _dbg(f"[{rname}] Final snapshot captured", 3)

    with ThreadPoolExecutor(max_workers=len(routers)) as ex:
        futs = [ex.submit(finalize_router, r) for r in routers]
        for _ in as_completed(futs):
            pass

    # Build results
    results = []
    for r in routers:
        rres = {'name': r, 'iface': router_results[r]['egress'], 'services': []}
        before = router_results[r]['before']
        after = router_results[r]['after']
        for port, proto in services:
            d = svc_tokens[(port, proto)]
            pre_c = f"TSIM_KSMS={run_id}:PREROUTING:{port}/{proto}"
            post_c = f"TSIM_KSMS={run_id}:POSTROUTING:{port}/{proto}"
            b_pkts, _ = extract_counter(before, pre_c)
            a_pkts, _ = extract_counter(after, pre_c)
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
                _dbg(f"[{r}] {port}/{proto}: pre {pre_delta} post {post_delta} -> {verdict}", 2)
            rres['services'].append({'port': port, 'protocol': proto, 'result': verdict})
        results.append(rres)

    if args.json:
        print(json.dumps({'source': args.source, 'destination': args.destination, 'routers': results}, indent=2))
    else:
        print(f"ksms: {args.source} -> {args.destination}")
        svc_str = ', '.join([f"{p}/{pr}" for p, pr in services])
        print(f"services: {svc_str}")
        for r in results:
            print(f"\nRouter {r['name']} [{r.get('iface') or '?'}]")
            for s in r['services']:
                print(f"  {s['port']}/{s['protocol']}: {s['result']}")

    # Exit with non-zero if any UNKNOWN (optional policy), else 0
    sys.exit(0)


if __name__ == '__main__':
    main()

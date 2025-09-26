# KSMS Tester (Kernel‑Space Multi‑Service Tester)

Fast, parallel, yes/no service reachability over FORWARD without userspace servers.

This document describes the design and implementation plan for a new tsimsh command `ksms_tester` and its backend `src/simulators/ksms_tester.py`.

## Goals
- Answer, per path‑router and per service (TCP/UDP port), whether packets from source to destination are forwarded (YES) or dropped (NO).
- Run all services in parallel, minimizing external process overhead.
- Avoid starting socat services or heavy client loops; emit a single kernel‑level probe per service.
- Leave the simulated environment exactly as it was (no re‑init needed).
- Match tsimsh UX conventions (help, JSON/text output, tab completion).

## High‑Level Approach
- Infer the list of involved routers from existing registries (hosts/bridges), exactly like other tsimsh commands (e.g., `service`). Input needed is only the source IP; real path discovery happens elsewhere and is out of scope.
- For each router (routers are analyzed independently, in parallel), insert two non‑terminating mangle counters (taps) that match only test packets:
  - PREROUTING: counts ingress of test packets.
  - POSTROUTING: counts egress after FORWARD (only if forwarded).
- On each router’s relevant egress (per its per‑router test topology, same as `service`), add a temporary static neighbor for the destination IP (ensures egress happens without ARP delay). Treat every router under test as "last" for the purposes of this isolated analysis.
- From the source netns, send one probe per service using a single userspace helper (Python) that emits:
  - TCP: one `connect_ex` attempt (SYN) per service with `IP_TOS` set (DSCP<<2).
  - UDP: one `sendto` datagram per service with `IP_TOS` set.
  The helper runs once inside the source netns and sends all probes in one process to minimize overhead. No destination namespace or server is required.
- Take baseline/final iptables counters (one `iptables-save -c` per router before and after emission), diff per service, decide YES/NO.
- Remove taps and static neighbor (idempotent cleanup), report results.

## CLI (tsimsh)
- Command: `ksms_tester`
- Arguments (Cmd2ArgumentParser):
  - `-s, --source <IP>`: required; choices from shell completer.
  - `-d, --destination <IP>`: required; choices from shell completer.
  - `-P, --ports "<spec>"`: multi‑service spec (same formats accepted by WSGI parser, e.g., `80,443/tcp,53/udp,22-25,telnet`), default protocol flag `--default-proto tcp|udp`.
  - `--max-services <N>`: default 10.
  - `--tcp-timeout <sec>`: TCP SYN connect timeout per service; default 1.0.
  - `-j, --json`: JSON output; otherwise human readable.
  - `-v, --verbose`: cumulative.
- Tab completion:
  - IP choices via `self.shell.completers._get_all_ips()`.
  - For `--ports` suggest quick/common ports from `TsimPortParserService`.
- Behavior mirrors `service`/`trace` command help and error handling.

## Backend Script
- New: `src/simulators/ksms_tester.py`
- Responsibilities:
  - Parse CLI; load facts/paths; resolve path routers and egress iface.
  - Parse port spec using `TsimPortParserService` (reuse WSGI service parser).
  - Allocate per‑service DSCP codes: dscp = 0x20 + index, tos = dscp << 2.
  - Insert taps, take baseline snapshots, configure static neighbor.
  - Emit probes via a single userspace helper once for all services from the source netns.
  - Final snapshots, diff counters, decide YES/NO, cleanup, print results.

## Detailed Flow
1) Parse input
- Source IP, destination IP.
- Service list via `TsimPortParserService.parse_port_spec(spec, default_proto, max_services)` → `[(port:int, proto:str), ...]`.

2) Router selection from registries
- Do NOT use `TracerouteSimulator`.
- Use the same registries and resolution logic other tsimsh commands use (e.g., `service`, `ping`) to determine which routers are involved for the given source IP. Typically this yields 1–3 routers.
- For each router, determine the egress interface to the destination IP by executing inside that router netns:
  - `ip route get <destination IP>`
  - Parse the first token after `dev` in the first output line; that interface is the egress (example: `1.1.1.1 via 192.168.122.1 dev enp1s0 ...` → egress `enp1s0`).
  - We treat each router as the "endpoint" of the per‑router test, so it needs its own static neighbor on that egress.

3) Token allocation
- For i,svc in enumerate(services): `dscp = 0x20 + i`, `tos = dscp << 2`.
- Keep `svc_tokens = { (port,proto): {dscp,tos,svc_id} }`.

4) Router preparation (parallel)
- For each router on path:
  - Build a single `iptables-restore -c` payload to:
    - Ensure `*mangle` section and declare `:TSIM_TAP_FW - [0:0]`.
    - Ensure `-A TSIM_TAP_FW -j RETURN` (empty user chain).
    - For each service:
      - `-I PREROUTING 1 -m dscp --dscp <dscp> -p <proto> --dport <port> -j TSIM_TAP_FW -m comment --comment "TSIM_KSMS=<run>:PREROUTING:<port>/<proto>"`
      - `-I POSTROUTING 1 -m dscp --dscp <dscp> -p <proto> --dport <port> -j TSIM_TAP_FW -m comment --comment "TSIM_KSMS=<run>:POSTROUTING:<port>/<proto>"`
    - `COMMIT`.
  - Apply once (no per‑rule exec loops).
  - Take baseline snapshot: `iptables-save -c -t mangle`.

5) Static neighbor (on each router under test)
- For every router involved, configure a static neighbor on the egress interface used in the per‑router test topology:
  - `ip neigh replace <dst_ip> lladdr 02:00:00:00:02:00 dev <egress_if> nud permanent`.
  - This mirrors how `service` isolates per‑router analysis: every router is analyzed independently (in parallel threads), and thus each router is treated as "last" for ARP purposes.

6) Emit probes (once)
- In source netns: invoke a single batch Python helper that sends all service probes:
  - For each service, set `IP_TOS = (dscp << 2)` on the socket.
  - For TCP, call `sock.connect_ex((dst_ip, port))` with the configured `--tcp-timeout` (default 1.0s) and close.
  - For UDP, call `sock.sendto(b"x", (dst_ip, port))` and close.
  - Run these per service in threads or sequentially; since it is one short‑lived process, overhead stays minimal.

7) Finalize and decide
- For each router (parallel): take final `iptables-save -c -t mangle`.
- Diff counters by matching comments for each service pair (PREROUTING/POSTROUTING):
  - If POSTROUTING delta > 0 → YES.
  - Else if PREROUTING delta > 0 and POSTROUTING delta == 0 → NO.
  - Else → UNKNOWN (not seen / inject issue).

8) Cleanup & Reconcile
- Post‑run: take final snapshots only (no tap/neighbor deletions). This keeps the end of run minimal.
- Pre‑run reconcile (every execution) removes any stale `TSIM_KSMS=` rules found in mangle PREROUTING/POSTROUTING via a single `iptables-restore -c` delete payload per router. This guarantees a clean starting state even after abnormal terminations.
- Static neighbor: use `ip neigh replace` during prepare to ensure correct ARP state for the current destination per router; no post‑run deletion is necessary. If needed, pre‑run can also `ip neigh del <dest_ip> dev <egress_if>` before `replace` for extra hygiene.

## Output Format
- Text (default):
  - Header: `ksms: <src> -> <dst> ; services: <summary>`
  - Per router: `Router <name> [<egress_if>]` then table‑style `port/proto: YES|NO|UNKNOWN`.
- JSON (`-j`):
  {
    "source": "10.1.1.1",
    "destination": "10.2.1.1",
    "routers": [
      {
        "name": "r1",
        "iface": "eth1",
        "services": [ {"port":80,"protocol":"tcp","result":"YES"}, ... ]
      }
    ]
  }

## Performance & Batching
- iptables changes: 1 restore (insert) + 1 restore (delete) per router.
- Snapshots: exactly 2 saves per router.
- Packet emission: single userspace helper process in source netns emitting all TCP/UDP probes.
- Parallelism: prepare/snapshot per router in a ThreadPool (size == routers). Emission is single step.
- No socat servers or long‑running clients; no kernel pktgen dependency.

## Error Handling
- If socket emission fails for a service (e.g., permission or transient error):
  - Report that service as UNKNOWN for the affected router and continue; always proceed to cleanup.
- If path/iface resolution fails:
  - Report router as UNKNOWN and continue.
- Always run cleanup in finally blocks.

## Parity with Existing Commands
- `Cmd2ArgumentParser`, help/usage consistency, `choices_provider` for IPs, quick ports suggestions.
- `-j` toggles JSON; `-v` controls debug prints.
- Shell command uses `BaseCommandHandler.run_script_with_output` to invoke simulator script.

## Files
- `src/shell/commands/ksms_tester.py` — CLI layer with parser, completion, and script invocation.
- `src/simulators/ksms_tester.py` — engine: batching, netns ops, probe emission (userspace), counters, cleanup, printing.
- (Optional) `docs/developers/ksms_tester.md` — developer notes (internals, test hints).

## Validation Plan
- Two‑router path with one ACCEPT and one DROP:
  - UDP 53: YES on r1, NO on r2 (or vice versa) per policy → verify counters.
  - TCP 80/443: verify SYN path and decision.
- Robustness: run back‑to‑back; ensure taps/neighbors fully removed; reconcile removes stale rules.
- Throughput: 10 services → total external process calls ~ O(routers), not O(routers×services).

## Future Enhancements
- eBPF tc classifier instead of iptables taps for even lighter per‑service counters.
- Optional per‑service TRACE for spot validation (one SYN only) on low‑confidence cases.
- Integrate configurable worker count and timeouts; expose via CLI flags.

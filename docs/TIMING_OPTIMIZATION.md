# Timing Optimization Playbook

## Baseline

- One-service baseline: 20 seconds = 1.00 unit (100%).
- Goals: reduce wall time and avoid linear growth with number of services.

## Current Reference (Already Implemented)

- Parallel router snapshots/analysis, in-process PDF, global cleanup:
  - 5 services: ~69.3s → ~46.9s (−32%).
  - Per-service unit (5 services): 46.9 / 20 = 2.35 units.

## Key Improvements (Percent vs. 1-Service Baseline = 20s)

- Reduce inter-service sleep (1.0s → 0.2–0.3s)
  - Savings: 0.7–0.8s per gap = 3.5–4.0% per extra service.
  - Effort: ~10–20 LoC.

- In-process packet analysis (no per-router subprocess)
  - Savings: ~0.5–1.0s per 5 services = 2.5–5.0%.
  - Effort: ~100–200 LoC.

- Tighten service test timeout (if safe, 1.0s → 0.7–0.8s)
  - Savings: 0.2–0.3s per service = 1.0–1.5% per service.
  - Effort: ~10–20 LoC + validation.

- PDF parallelization (render across ProcessPool)
  - Savings: ~1.0s per 5 services = 5.0%.
  - Effort: ~50–100 LoC.

- Quick PDF mode (summary-only / failed-only)
  - Savings: ~1.0–1.4s per 5 services = 5.0–7.0%.
  - Effort: ~50–100 LoC.

- Phase 2 micro-parallelization (start/stop services with small pool)
  - Savings: ~1–2s per run (5 services) = 5–10%.
  - Effort: ~80–150 LoC.

- Pre-allocate hosts (persistent; batch create outside WSGI)
  - Savings: ~6–7s per run = 30–35%.
  - Effort: 300–500 LoC (tsimsh host command + setup).

- Direct ip netns for snapshots/tests (bypass tsimsh)
  - Savings: ~3–5s per 5 services = 15–25%.
  - Effort: 300–600 LoC.

- nft trace integration (RHEL 8/9)
  - Savings: ~3–5s per 5 services = 15–25%; higher fidelity.
  - Effort: 400–800 LoC (trace rules/monitor/fallbacks).

- Vectorized counting (nft sets with per-element counters; ipset on RHEL 7)
  - Savings: converts O(N) to near-constant wall time for large N (e.g., 200 services ≈ single-service time + a few seconds).
  - Effort: 400–700 LoC.

- Horizontal sharding (runner pool)
  - Savings: T ≈ ceil(services/runners) × single-service time + 2–5s orchestration.
  - Effort: 200–400 LoC (orchestrator + artifact merge).

## Scenario Comparison (Wall-Time)

| Approach                      | 1 svc (units) | 1 svc (sec) | 5 svcs (sec) | 200 svcs (sec)      |
|------------------------------|---------------:|------------:|-------------:|--------------------:|
| Current optimized serial     |          1.00 |          20 |          ~47 | impractical (linear)|
| + Reduce inter-service sleep |          1.00 |          20 |          ~44 | −0.7×(N−1) (large)  |
| + Tighten timeouts           |    0.98–0.99   | 19.7–19.8   |       ~43–44 | linear, lower slope |
| + Pre-allocate hosts (persist)|   0.65–0.70   |     13–14   |       ~40–41 | linear −6–7s offset |
| + Direct ip netns path       |    0.95–0.98   |     19–19.5 |       ~42–44 | linear, lower slope |
| nft trace (RHEL 8/9)         |         ~1.00 |         ~20 |       22–28  | 22–28               |
| Vectorized counting (nft/ipset)|       ~1.00 |         ~20 |       22–28  | 22–28               |
| 10 parallel runners          |         ~1.00 |         ~20 |       22–27  | 22–30               |
| Vectorized + runners         |         ~1.00 |         ~20 |       20–25  | 20–25               |

Notes:
- Units normalized to 20s baseline = 1.00.
- Ranges depend on topology, router count, success/failure mix, and PDF mode.
- Vectorized counting and nft trace deliver near-constant scaling.

## Effort vs Benefit (LoC and % of Baseline)

| Improvement                    | Est. LoC | Save per baseline (%) | Save (5 svcs, sec) | Notes                           |
|--------------------------------|---------:|----------------------:|-------------------:|----------------------------------|
| Reduce inter-service sleep     |   10–20  | n/a; per gap 3.5–4.0% |          ~2.8–3.2  | Major for many services          |
| In-process analysis            | 100–200  | 2.5–5.0               |          ~0.5–1.0  | Easy gain                        |
| Tighten timeouts               |   10–20  | 1.0–1.5 per service   |            ~1–2    | Validate correctness             |
| PDF parallelization            |   50–100 | 5.0                   |              ~1.0  | Minor                            |
| Quick PDF mode                |   50–100 | 5.0–7.0               |          ~1.0–1.4  | Policy-driven                    |
| Phase 2 micro-parallel         |   80–150 | 5–10                  |              ~1–2  | Safe, bounded pool               |
| Pre-allocate hosts (persist)   | 300–500  | 30–35                 |              ~6–7  | Requires tsimsh changes          |
| Direct ip netns path           | 300–600  | 15–25 (per 5 svcs)    |              ~3–5  | Privileged ops                   |
| nft trace                      | 400–800  | 15–25 (per 5 svcs)    |              ~3–5  | RHEL8/9; best fidelity           |
| Vectorized counting            | 400–700  | 90%+ (for large N)    | ~constant time     | nft sets/ipset counters          |
| 10-runner sharding             | 200–400  | 90%+ (for large N)    | ~constant time     | Needs coordination               |

## Vectorized Counting: What and How

- Concept: Replace per-service “snapshot → single test → snapshot → parse” with a single counter-capable rule matching a set of services. Send probes for all services concurrently; read counters once.

- nftables (RHEL 8/9): per-element counters in sets.
  - Create a set per router namespace containing tuples for all services under test (e.g., protocol,dport[,src,dst]).
  - Install a rule that matches the set and increments per-element counters.
  - Send stateless probes for all services concurrently (TCP SYNs or small UDP packets).
  - Read the set once; element deltas are per-service decisions.

- iptables + ipset (RHEL 7): similar vectorization via ipset with counters and a single iptables match.

### Correct Implementation Steps

1. Per router namespace, install a counting rule:
   - nft example:
     - `table inet tsim {`
     - `  set svc { type inet_service; flags dynamic,timeout,counter; }`
     - `  chain fwd { type filter hook forward priority 0; policy accept;`
     - `    ip saddr <src> ip daddr <dst> tcp dport @svc counter; }`
     - `}`
   - ipset example:
     - `ipset create svc hash:ip,port counters`
     - `iptables -A FORWARD -s <src> -d <dst> -m set --match-set svc dst -p tcp -j RETURN` (or a dedicated target).

2. Populate the set with all services under test (include protocol; include IPs to scope, if needed).

3. Reset/flush counters at the start of the run.

4. Fire probes concurrently:
   - TCP: SYN (RST acceptable for reachability). 
   - UDP: one or two small packets to avoid transient loss.

5. Read counters once:
   - nft: `nft -a list set inet tsim svc` (parse per-element counters).
   - ipset: `ipset save svc` (parse counters).

6. Classify:
   - If per-router counter for a service increased → allowed at that router; otherwise blocked. Combine across routers for end-to-end result.

7. Cleanup:
   - Remove rules/sets or leave in place and reset counters for reuse.

### Gotchas and Best Practices

- Scope flows tightly (src/dst IP, protocol, dport) to avoid unrelated traffic inflating counts.
- NAT/conntrack: Count on pre-NAT side for classification or mirror both directions carefully.
- UDP: Use a few probes; still cheaper than per-service sleeps.
- RHEL 7: ipset counters provide slightly lower performance than nft sets but still near-constant time for large N.
- Security: Requires CAP_NET_ADMIN inside namespaces; use a privileged helper if needed.

## Bottom Line

- Small, low-risk tweaks yield 10–20% improvements (sleep, timeouts, micro-parallelism).
- Medium changes (pre-allocate hosts, ip netns path, nft trace) yield 15–35% with better fidelity.
- Architectural shifts (vectorized counting, horizontal sharding) break linear scaling:
  - 200 services run in roughly single-service time + a few seconds (~20–30s), transforming a multi-minute workload into seconds on current hardware/software.


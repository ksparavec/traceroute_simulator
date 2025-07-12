# Implementation Plan: Advanced Network Simulation Enhancement

## Overview
This document outlines the comprehensive plan to enhance the traceroute simulator with advanced network simulation capabilities, including complex iptables rules, policy routing, ipsets, and full packet tracing.

## Git Branch Strategy

### Primary Branches Structure
```
main
├── task1-raw-facts-enhancement
│   ├── task1.1-iptables-rules
│   ├── task1.2-policy-routing
│   └── task1.3-ipset-configurations
├── task2-netns-simulator-enhancement
│   ├── task2.1-raw-facts-loading
│   ├── task2.2-mtr-options-implementation
│   ├── task2.3-iptables-logging
│   └── task2.4-packet-tracing
└── integration-branch (merges task1 + task2)
```

## Task 1: Raw Facts Enhancement

### Task 1.1: Iptables Rules Enhancement
**Branch**: `task1.1-iptables-rules`
**Goal**: Add comprehensive iptables rules allowing ping/mtr between all routers/hosts

#### Implementation Details:
- **Filter Table Rules**:
  - FORWARD chain: Allow ICMP, TCP, UDP between all internal networks
  - INPUT/OUTPUT chains: Allow necessary protocols for MTR/ping
  - Logging rules for packet tracing

- **NAT Table Rules**:
  - POSTROUTING masquerading for internet access
  - PREROUTING DNAT rules for service access

- **Mangle Table Rules**:
  - Packet marking for QoS and routing decisions
  - TTL modifications for advanced scenarios

#### Files to Modify:
- `tests/raw_facts/*_facts.txt` (all 10 router files)

#### Testing Strategy:
- Create `tests/test_enhanced_iptables_rules.py`
- Add `make test-iptables-enhanced` target

### Task 1.2: Policy Routing Enhancement
**Branch**: `task1.2-policy-routing`
**Goal**: Add complex policy routing with multiple routing tables

#### Implementation Details:
- **Minimum 3 policies per router**:
  - Source-based routing (per network segment)
  - Service-based routing (per port/protocol)
  - QoS-based routing (priority traffic)

- **Additional Routing Tables**:
  - `priority_table` (table 100): High-priority traffic
  - `service_table` (table 200): Service-specific routes
  - `backup_table` (table 300): Backup/failover routes

#### Enhanced Sections:
- `policy_rules`: Multiple ip rule entries
- `routing_tables_*`: Additional table content
- `route_cache`: Enhanced cache entries

#### Files to Modify:
- Add routing table sections to all raw facts files
- Update facts processing scripts

#### Testing Strategy:
- Create `tests/test_policy_routing_enhancement.py`
- Add `make test-policy-routing` target

### Task 1.3: Ipset Configurations
**Branch**: `task1.3-ipset-configurations`
**Goal**: Implement comprehensive ipset examples covering all syntax types

#### Implementation Details:
Based on ipset documentation, implement:

**Bitmap Sets**:
```bash
# bitmap:ip - Host/network addresses
ipset create internal_hosts bitmap:ip range 10.1.1.0/24
ipset create dmz_networks bitmap:ip range 10.1.2.0-10.1.5.255

# bitmap:ip,mac - IP/MAC pairs for security
ipset create secure_clients bitmap:ip,mac range 10.1.1.0/24

# bitmap:port - Port ranges
ipset create web_ports bitmap:port range 80-8080
ipset create db_ports bitmap:port range 3306-5432
```

**Hash Sets**:
```bash
# hash:ip - Simple IP lists
ipset create management_ips hash:ip timeout 3600
ipset create blacklisted_ips hash:ip counters comment

# hash:net - Network ranges
ipset create internal_networks hash:net family inet
ipset create vpn_networks hash:net family inet maxelem 1024

# hash:ip,port - Service-specific sets
ipset create web_services hash:ip,port timeout 7200
ipset create database_access hash:ip,port counters

# hash:net,iface - Interface-specific networks
ipset create interface_networks hash:net,iface
ipset create trusted_networks hash:net,iface timeout 1800

# Advanced multi-dimensional sets
ipset create complex_rules hash:ip,port,net
ipset create service_matrix hash:ip,port,ip timeout 600
```

#### Files to Modify:
- Add comprehensive ipset sections to all raw facts files
- Implement ipset population scripts

#### Testing Strategy:
- Create `tests/test_ipset_configurations.py` 
- Add `make test-ipsets` target

## Task 2: Network Namespace Simulator Enhancement

### Task 2.1: Raw Facts Direct Loading
**Branch**: `task2.1-raw-facts-loading`
**Goal**: Modify netns simulator to load directly from raw facts

#### Implementation Details:
- **New Parser Module**: `src/core/raw_facts_parser.py`
  - Parse all TSIM_SECTION blocks
  - Convert to internal data structures
  - Handle all fact types (routing, iptables, ipsets, etc.)

- **Modified Files**:
  - `src/simulators/network_namespace_setup.py`
  - `src/simulators/network_namespace_tester.py`
  - `src/simulators/network_namespace_status.py`

- **Removed Dependencies**:
  - Remove JSON facts loading (except metadata)
  - Eliminate intermediate processing steps

#### Testing Strategy:
- Create `tests/test_raw_facts_loading.py`
- Add `make test-raw-facts-loading` target

### Task 2.2: MTR Options Implementation
**Branch**: `task2.2-mtr-options-implementation`
**Goal**: Add advanced MTR options support

#### New Command Line Options:
```bash
--mtr-src <source_ip>        # Source IP for MTR
--mtr-dst <destination_ip>   # Destination IP for MTR  
--mtr-src-port <port>        # Source port
--mtr-dst-port <port>        # Destination port
--mtr-proto <protocol>       # Protocol (icmp/udp/tcp)
--mtr-timeout <seconds>      # MTR timeout
```

#### Implementation Details:
- **Enhanced MTR Executor**: `src/executors/enhanced_mtr_executor.py`
  - Support all MTR command-line options
  - Protocol-specific execution modes
  - Advanced timeout handling
  
- **Integration Points**:
  - Namespace tester integration
  - Policy routing consideration
  - Firewall rule validation

#### Testing Strategy:
- Create `tests/test_mtr_options.py`
- Add `make test-mtr-options` target

### Task 2.3: Iptables Logging Implementation  
**Branch**: `task2.3-iptables-logging`
**Goal**: Implement comprehensive iptables rule logging

#### Implementation Details:
- **Enhanced Raw Facts**: Add LOG targets to all rules
  ```bash
  iptables -A FORWARD -j LOG --log-prefix "FWD-ALLOW: " --log-level 4
  iptables -A FORWARD -s 10.1.1.0/24 -d 10.2.1.0/24 -j ACCEPT
  ```

- **Log Processing Engine**: `src/analyzers/iptables_log_processor.py`
  - Parse kernel logs from each namespace
  - Extract rule trigger events
  - Correlate with rule database

- **NetLog Script**: `scripts/netlog`
  ```bash
  ./scripts/netlog --source 10.1.1.1 --dest 10.2.1.1 --time-range "10:00-11:00"
  ./scripts/netlog --router hq-gw --port 80 --last 100
  ./scripts/netlog --all-routers --protocol icmp
  ```

#### New Files:
- `src/analyzers/iptables_log_processor.py`
- `scripts/netlog`
- `src/core/log_filter.py`

#### Testing Strategy:
- Create `tests/test_iptables_logging.py`
- Add `make test-netlog` target

### Task 2.4: Full Packet Tracing
**Branch**: `task2.4-packet-tracing`
**Goal**: Implement comprehensive packet tracing through network

#### Implementation Details:
- **Packet Tracer Engine**: `src/analyzers/packet_tracer.py`
  - Trace packet path through all routers
  - Show triggered rules at each hop
  - Display routing decisions
  - Show policy rule matches

- **Rule Database**: `src/core/rule_database.py`
  - Store all iptables rules with numbers
  - Map rule numbers to actual rules
  - Cross-reference with log entries

- **Enhanced Output**:
  ```
  Packet Trace: 10.1.1.1 -> 10.2.1.1 (ICMP)
  
  Router: hq-gw (10.1.1.1)
  ├─ Policy Rule: from 10.1.1.0/24 lookup main (table 254)
  ├─ Routing: 10.2.0.0/16 via 10.1.2.1 dev eth0 metric 10
  ├─ Iptables FORWARD Rule #3: ACCEPT -s 10.1.1.0/24 -d 10.2.0.0/16 -p icmp
  └─ Exit Interface: eth0 -> 10.1.2.1
  
  Router: br-gw (10.1.2.1)
  ├─ Policy Rule: from all lookup main (table 254)  
  ├─ Routing: 10.2.1.0/24 dev eth1 proto kernel scope link
  ├─ Iptables FORWARD Rule #5: ACCEPT -d 10.2.1.0/24 -p icmp
  └─ Exit Interface: eth1 -> 10.2.1.1
  ```

#### New Files:
- `src/analyzers/packet_tracer.py`
- `src/core/rule_database.py`
- `src/core/routing_simulator.py`
- `scripts/packet-trace`

#### Testing Strategy:
- Create `tests/test_packet_tracing.py`
- Add `make test-packet-trace` target

## Testing Strategy

### Enhanced Make Targets
```makefile
# Individual task testing
test-iptables-enhanced: Test enhanced iptables rules
test-policy-routing: Test policy routing configurations  
test-ipsets: Test ipset configurations
test-raw-facts-loading: Test direct raw facts loading
test-mtr-options: Test advanced MTR options
test-netlog: Test iptables logging system
test-packet-trace: Test full packet tracing

# Combined testing
test-task1: Run all Task 1 tests
test-task2: Run all Task 2 tests  
test-enhanced: Run all enhancement tests
```

### Test Coverage Requirements
- **Minimum 95% code coverage** for new functionality
- **Integration tests** for cross-component interactions
- **Performance tests** for large-scale scenarios
- **Error handling tests** for failure scenarios

## Implementation Timeline

### Phase 1: Raw Facts Enhancement (Task 1)
- **Week 1**: Iptables rules enhancement (1.1)
- **Week 2**: Policy routing enhancement (1.2)  
- **Week 3**: Ipset configurations (1.3)
- **Week 4**: Integration and testing

### Phase 2: Simulator Enhancement (Task 2)
- **Week 5**: Raw facts loading (2.1)
- **Week 6**: MTR options implementation (2.2)
- **Week 7**: Iptables logging (2.3)
- **Week 8**: Packet tracing (2.4)

### Phase 3: Integration & Testing
- **Week 9**: Branch integration
- **Week 10**: Full system testing
- **Week 11**: Performance optimization
- **Week 12**: Documentation and deployment

## Success Criteria

### Task 1 Success Criteria:
- All 10 raw facts files enhanced with complex configurations
- Ping/MTR connectivity between all routers/hosts
- Minimum 3 policy rules per router with additional routing tables  
- Comprehensive ipset examples covering all syntax types
- All tests passing with >95% coverage

### Task 2 Success Criteria:
- Netns simulator loads directly from raw facts (no JSON dependency)
- All MTR options implemented and functional
- Complete iptables logging with rule correlation
- Full packet tracing showing rule triggers and routing decisions
- NetLog script providing flexible log filtering
- All tests passing with >95% coverage

### Integration Success Criteria:
- End-to-end packet tracing from source to destination
- Complex routing scenarios working correctly
- Firewall rules properly enforced and logged
- Performance suitable for hundreds of router simulation
- Comprehensive test suite covering all scenarios

## Risk Mitigation

### Technical Risks:
- **Memory usage**: Implement efficient data structures for large configurations
- **Performance**: Use caching and optimized algorithms for packet tracing
- **Complexity**: Modular design with clear interfaces between components

### Implementation Risks:
- **Scope creep**: Strict adherence to defined requirements
- **Integration issues**: Regular integration testing throughout development
- **Test coverage**: Automated coverage reporting and enforcement

This implementation plan provides a comprehensive roadmap for creating a production-ready network simulation system capable of handling hundreds of routers with complex configurations and full packet tracing capabilities.
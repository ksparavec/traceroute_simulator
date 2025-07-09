# Network Namespace Wrapper Design

## Overview

This document analyzes the design requirements for comprehensive network namespace wrappers to replace sudo requirements across all namespace-related scripts in the traceroute simulator project.

## Current Script Requirements

### Scripts Requiring Privileged Operations

| Script | Purpose | Key Operations Required |
|--------|---------|------------------------|
| `netsetup` | Network namespace creation | Create namespaces, bridges, veth pairs, IP config, routing |
| `netclean` | Network cleanup | Delete namespaces, cleanup veth pairs, remove bridges |
| `netnsclean` | Comprehensive cleanup | Remove all namespaces and associated resources |
| `hostadd` | Host management | Create host namespace, veth pairs, connect to bridges |
| `hostdel` | Host removal | Remove host namespace, cleanup interfaces |
| `hostlist` | Host listing | Read host registry (read-only capable) |
| `hostclean` | Host cleanup | Remove all hosts |
| `svcstart` | Service management | Start services in namespaces (socat processes) |
| `svcstop` | Service termination | Kill services by PID |
| `svclist` | Service listing | List running services (mostly read operations) |
| `svcclean` | Service cleanup | Stop all services |
| `nettest` | Network testing | Enter namespace, run network tests (ping, nc, etc.) |
| `svctest` | Service testing | Service connectivity testing |
| `netstatus` | Status monitoring | Read operations (already covered by existing wrapper) |

## Comprehensive Operations Analysis

### Core Network Operations
- **Namespace Management**: Create, delete, list namespaces
- **Interface Management**: Create/delete veth pairs, bridges, move interfaces
- **IP Configuration**: Add/remove IP addresses, routes, policy rules
- **Bridge Operations**: Create bridges, attach/detach interfaces
- **Process Management**: Start/stop processes in namespaces

### Required Capabilities
- `CAP_SYS_ADMIN` - Namespace creation and management
- `CAP_NET_ADMIN` - Network interface and routing configuration
- `CAP_KILL` - Process termination for service management
- `CAP_SETUID`/`CAP_SETGID` - Process execution in namespaces

## Architecture Options

### Option 1: Monolithic Wrapper
Single comprehensive wrapper handling all operations.

**Pros:**
- Single binary to manage
- Consistent security model
- Shared validation code

**Cons:**
- Large attack surface (~2000+ lines)
- Complex to maintain
- Single point of failure

### Option 2: Specialized Wrappers (Recommended)
Multiple focused wrappers for different operation categories.

#### Wrapper Categories:

1. **`netns_network`** - Network Infrastructure
   - Operations: `create`, `delete`, `veth-add`, `bridge-add`, `ip-add`, `route-add`, `rule-add`
   - Target scripts: `netsetup`, `netclean`, `netnsclean`
   - Complexity: ~600 lines

2. **`netns_service`** - Service Management
   - Operations: `start`, `stop`, `list`, `exec`, `kill`
   - Target scripts: `svcstart`, `svcstop`, `svclist`, `svcclean`
   - Complexity: ~400 lines

3. **`netns_host`** - Host Management
   - Operations: `add`, `delete`, `list`, `connect`, `disconnect`
   - Target scripts: `hostadd`, `hostdel`, `hostlist`, `hostclean`
   - Complexity: ~400 lines

4. **`netns_test`** - Testing Operations
   - Operations: `ping`, `tcp-test`, `udp-test`, `mtr`, `exec`
   - Target scripts: `nettest`, `svctest`
   - Complexity: ~300 lines

5. **`netns_reader`** - Read Operations (Existing)
   - Operations: Various read-only commands
   - Target scripts: `netstatus`
   - Complexity: ~200 lines (already implemented)

## Detailed Operation Specifications

### Network Infrastructure Operations (`netns_network`)

```c
// Operation syntax
netns_network create <namespace>
netns_network delete <namespace>
netns_network veth-add <veth1> <veth2>
netns_network bridge-add <bridge> [namespace]
netns_network ip-add <interface> <ip/prefix> [namespace]
netns_network route-add <route> [namespace]
netns_network rule-add <rule> [namespace]
netns_network link-up <interface> [namespace]
netns_network link-attach <interface> <bridge> [namespace]
```

**Validation Requirements:**
- Namespace names: alphanumeric + hyphens, max 64 chars
- Interface names: standard Linux interface naming
- IP addresses: IPv4/IPv6 CIDR validation
- Route syntax: standard Linux route format
- No path traversal or shell injection

### Service Management Operations (`netns_service`)

```c
// Operation syntax
netns_service start <namespace> <service_type> <bind_ip> <port> [options]
netns_service stop <pid>
netns_service list [namespace]
netns_service exec <namespace> <command>
netns_service kill-all [namespace]
```

**Validation Requirements:**
- Service types: tcp, udp only
- Port ranges: 1-65535
- IP binding: valid IP addresses only
- Command whitelist for exec operations
- PID validation for kill operations

### Host Management Operations (`netns_host`)

```c
// Operation syntax
netns_host add <hostname> <primary_ip> <connect_router> [secondary_ips...]
netns_host delete <hostname>
netns_host list [format]
netns_host connect <hostname> <router>
netns_host disconnect <hostname> <router>
```

**Validation Requirements:**
- Hostname format: DNS-compatible names
- IP validation: CIDR notation
- Router validation: exists in registry
- Registry file locking for concurrent access

### Testing Operations (`netns_test`)

```c
// Operation syntax
netns_test ping <namespace> <destination> [count]
netns_test tcp-test <namespace> <destination> <port>
netns_test udp-test <namespace> <destination> <port> [message]
netns_test mtr <namespace> <destination> [hops]
netns_test exec <namespace> <whitelisted_command>
```

**Validation Requirements:**
- Command whitelist: ping, nc, socat, mtr only
- Destination validation: IP addresses or resolvable names
- Port validation: 1-65535
- Hop count limits: 1-30 for mtr

## Security Considerations

### Input Validation
- **Strict parameter validation** for all operations
- **No shell execution** - direct system calls or exec only
- **Whitelist approach** for all commands and parameters
- **Length limits** on all string inputs
- **Format validation** for IP addresses, CIDRs, interface names

### Privilege Management
- **Minimal capabilities** - only required caps per wrapper
- **Drop privileges** after initialization
- **No setuid root** - use file capabilities
- **Separate user/group** for wrapper execution

### Audit and Logging
- **Operation logging** to syslog
- **Error logging** with context
- **Success/failure tracking**
- **Rate limiting** to prevent resource exhaustion

### Error Handling
- **Graceful failure modes**
- **Resource cleanup** on errors
- **Atomic operations** where possible
- **Rollback capability** for complex operations

## Implementation Strategy

### Phase 1: Core Network Wrapper
1. Implement `netns_network` wrapper
2. Update `netsetup`, `netclean`, `netnsclean` scripts
3. Comprehensive testing with namespace operations

### Phase 2: Service Management
1. Implement `netns_service` wrapper
2. Update service management scripts
3. Test service lifecycle operations

### Phase 3: Host Management
1. Implement `netns_host` wrapper
2. Update host management scripts
3. Test dynamic host operations

### Phase 4: Testing Support
1. Implement `netns_test` wrapper
2. Update testing scripts
3. Integration testing across all wrappers

## File Structure

```
src/utils/
├── netns_reader.c          # Existing read-only wrapper
├── netns_network.c         # Network infrastructure wrapper
├── netns_service.c         # Service management wrapper
├── netns_host.c           # Host management wrapper
├── netns_test.c           # Testing operations wrapper
├── netns_common.h         # Shared validation functions
└── netns_common.c         # Common utility functions
```

## Testing Strategy

### Unit Testing
- Individual operation validation
- Error condition handling
- Security boundary testing
- Input validation testing

### Integration Testing
- Cross-wrapper interactions
- Registry file consistency
- Resource cleanup verification
- Performance under load

### Security Testing
- Privilege escalation attempts
- Input injection testing
- Resource exhaustion testing
- Audit trail verification

## Migration Path

1. **Parallel deployment** - Deploy wrappers alongside existing sudo scripts
2. **Gradual migration** - Update one script category at a time
3. **Fallback support** - Maintain sudo fallback during transition
4. **Validation period** - Extensive testing before removing sudo dependencies
5. **Documentation updates** - Update all documentation and examples

## Estimated Complexity

| Component | Lines of Code | Development Time | Testing Time |
|-----------|---------------|------------------|--------------|
| netns_network | ~600 | 2-3 weeks | 1-2 weeks |
| netns_service | ~400 | 1-2 weeks | 1 week |
| netns_host | ~400 | 1-2 weeks | 1 week |
| netns_test | ~300 | 1 week | 1 week |
| Common utilities | ~200 | 1 week | - |
| Testing & validation | - | 1 week | 2 weeks |
| **Total** | **~1900** | **6-9 weeks** | **5-6 weeks** |

## Conclusion

A comprehensive wrapper system is feasible but represents significant development effort. The specialized wrapper approach is recommended for:
- Reduced attack surface per component
- Easier maintenance and updates
- Logical separation of concerns
- Incremental deployment capability

The estimated 11-15 week development timeline makes this a substantial project that should be carefully planned and executed in phases.
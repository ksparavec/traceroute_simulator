# Traceroute Simulator Documentation

## Documentation by Audience

This documentation is organized for three distinct audiences with different needs and technical backgrounds:

### 📱 [Web Users](web-users/README.md)
For users accessing the system through the web interface to analyze firewall configurations and generate reports.

**You'll learn:**
- How to login and navigate the web interface
- Running network connectivity tests
- Understanding test results and status indicators
- Generating and interpreting PDF reports
- Common troubleshooting scenarios

**Start here if you:**
- Use the web browser interface
- Need to test firewall rules
- Generate compliance reports
- Don't work with command-line tools

---

### 🔧 [System Administrators](sysadmins/README.md)
For administrators who deploy, configure, and maintain the traceroute simulator system.

**You'll learn:**
- Complete installation and setup procedures
- Using tsimsh interactive shell effectively
- Managing network namespaces and simulations
- Collecting router data with Ansible
- Security configuration and sudoers setup
- Using make targets for automation

**Start here if you:**
- Deploy and maintain the system
- Configure routers and collect facts
- Manage user access and security
- Need to troubleshoot system issues
- Write automation scripts

---

### 💻 [Python Developers](developers/README.md)
For developers who need to understand, modify, or extend the codebase.

**You'll learn:**
- System architecture and design patterns
- Code organization and module structure
- How core components work internally
- Implementing new tsimsh commands
- Firewall analysis engine details
- Testing framework and development workflow

**Start here if you:**
- Need to modify or extend the code
- Add new features or commands
- Fix bugs or improve performance
- Understand the implementation details
- Contribute to the project

---

## Quick Navigation

### Essential Topics

#### For Everyone
- [System Overview](sysadmins/README.md#system-overview)
- [Getting Help](web-users/README.md#getting-help)

#### Getting Started
- [Web Interface First Steps](web-users/README.md#getting-started)
- [tsimsh Quick Start](sysadmins/README.md#tsimsh---the-interactive-shell)
- [Development Setup](developers/README.md#development-workflow)

#### Key Features
- [Running Network Tests](web-users/README.md#running-network-tests)
- [Network Namespace Simulation](sysadmins/README.md#linux-namespace-simulation)
- [Firewall Analysis Engine](developers/README.md#firewall-analysis-engine)

#### Configuration
- [Web Interface Setup](sysadmins/README.md#web-interface-setup)
- [Ansible Data Collection](sysadmins/README.md#data-collection-with-ansible)
- [Security Configuration](sysadmins/README.md#security-configuration)

#### Reference
- [Make Targets](sysadmins/README.md#make-targets-reference)
- [tsimsh Commands](sysadmins/README.md#command-categories)
- [Python API](developers/README.md#core-components)

#### Troubleshooting
- [Web Interface Issues](web-users/README.md#troubleshooting)
- [System Issues](sysadmins/README.md#troubleshooting-and-maintenance)
- [Development Issues](developers/README.md#troubleshooting-development-issues)

---

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   User Interfaces                        │
├─────────────┬──────────────┬──────────────┬────────────┤
│  Web GUI    │   tsimsh     │ Command Line │  Ansible   │
│  (Browser)  │ (Interactive)│   (Direct)   │ (Remote)   │
└──────┬──────┴──────┬───────┴──────┬───────┴─────┬──────┘
       │             │              │              │
       ▼             ▼              ▼              ▼
┌──────────────────────────────────────────────────────────┐
│              Core Python Engine (src/)                   │
├──────────────────────────────────────────────────────────┤
│ • TracerouteSimulator  - Path calculation                │
│ • IptablesAnalyzer    - Firewall rule analysis          │
│ • NamespaceManager    - Virtual network creation        │
│ • ServiceManager      - TCP/UDP service testing         │
│ • PacketTracer        - Detailed packet flow            │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                    Data Layer                            │
├──────────────────────────────────────────────────────────┤
│ • Router Facts (JSON) - Configuration data               │
│ • Raw Facts (Text)    - Original router output          │
│ • Network Topology    - Connection mapping              │
│ • Host Registry       - Dynamic host tracking           │
└──────────────────────────────────────────────────────────┘
```

## Network Topology

The included test network demonstrates a typical enterprise setup:

```
    Headquarters (HQ)              Branch Office              Data Center
    ┌──────────────┐              ┌──────────────┐          ┌──────────────┐
    │    hq-gw     │◄═══WG0═══►   │    br-gw     │◄══WG1══► │    dc-gw     │
    │  10.1.1.1    │               │  10.2.1.1    │          │  10.3.1.1    │
    └──────┬───────┘               └──────┬───────┘          └──────┬───────┘
           │                              │                         │
    ┌──────▼───────┐              ┌──────▼───────┐          ┌──────▼───────┐
    │   hq-core    │              │   br-core    │          │   dc-core    │
    │  10.1.2.1    │              │  10.2.1.2    │          │  10.3.1.2    │
    └──┬────────┬──┘              └──────┬───────┘          └──────┬───────┘
       │        │                        │                         │
  ┌────▼──┐ ┌───▼──┐              ┌──────▼───────┐          ┌──────▼───────┐
  │hq-dmz │ │hq-lab│              │   br-wifi    │          │   dc-srv     │
  └───────┘ └──────┘              └──────────────┘          └──────────────┘

  WG0/WG1 = WireGuard VPN Tunnels
```

## Data Flow Example

Here's how a typical trace works:

```
User Request: Trace from 10.1.1.1 to 10.2.1.1

1. Web Interface / tsimsh
   └─> Receives user input
   
2. TracerouteSimulator
   ├─> Loads router facts from JSON
   ├─> Finds source router (hq-gw)
   └─> Calculates path using routing tables
   
3. Path Calculation
   ├─> hq-gw: Route lookup → next hop via wg0
   ├─> br-gw: Received on wg0 → route to local
   └─> Destination reached
   
4. Firewall Analysis
   ├─> Check hq-gw FORWARD rules
   ├─> Check br-gw INPUT rules  
   └─> Determine ALLOW/BLOCK status
   
5. Response Formatting
   ├─> Generate hop-by-hop output
   ├─> Create network diagram (optional)
   └─> Return to user interface
```

## Key Concepts

### Router Facts
JSON files containing complete router configuration including interfaces, routes, firewall rules, and metadata. Located in `$TRACEROUTE_SIMULATOR_FACTS`.

### Network Namespaces
Linux kernel feature providing network isolation. Each namespace acts as a virtual router with independent network stack.

### tsimsh
Interactive shell providing user-friendly commands with tab completion, scripting support, and batch processing capabilities.

### Make Targets
Predefined automation commands in Makefile for common operations like testing, setup, and data collection.

## Getting Help

- **Web Users**: Contact your system administrator for login credentials and access issues
- **System Administrators**: Review logs in `/var/log/` and use `make test` for diagnostics
- **Developers**: Enable debug mode with `TRACEROUTE_SIMULATOR_DEBUG=1` and check test coverage

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on:
- Code style and standards
- Testing requirements
- Pull request process
- Issue reporting

## License

This project is licensed under the terms specified in [LICENSE](../LICENSE).
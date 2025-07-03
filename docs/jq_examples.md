# JQ Commands for Extracting Network Facts from JSON Files

This document provides useful `jq` commands for extracting routing rules, routes, iptables, and ipsets from processed JSON facts files.

## Prerequisites

The JSON file should be processed with interface parsing enabled:
```bash
python3 ansible/process_all_facts.py --verbose
```

## 1. Routing Rules

```bash
# List all routing rules
cat router.json | jq '.routing.rules'

# Get rule summary (priority, table, source)
cat router.json | jq '.routing.rules | map({priority: .priority, table: .table, src: .src})'

# Count total rules
cat router.json | jq '.routing.rules | length'

# Get rules for specific table
cat router.json | jq '.routing.rules | map(select(.table == "main"))'

# Get rules by priority range
cat router.json | jq '.routing.rules | map(select(.priority >= 100 and .priority <= 1000))'
```

## 2. Routing Tables

```bash
# List all routing table entries
cat router.json | jq '.routing.tables'

# Count routing entries
cat router.json | jq '.routing.tables | length'

# Get entries per routing table
cat router.json | jq '.routing.tables | group_by(.table) | map({table: .[0].table, entries: length})'

# Get destinations only
cat router.json | jq '.routing.tables | map(.dst)'

# Get default routes
cat router.json | jq '.routing.tables | map(select(.dst == "default"))'

# Get routes for specific subnet
cat router.json | jq '.routing.tables | map(select(.dst | startswith("10.1")))'

# Get routing table names mapping
cat router.json | jq '.routing.table_names'

# Get routes from specific table
cat router.json | jq '.routing.tables | map(select(.table == "main"))'
```

## 3. Interface Information

```bash
# List all interface names
cat router.json | jq '.network.interfaces.parsed | keys'

# Get interface states
cat router.json | jq '.network.interfaces.parsed | to_entries | map({interface: .key, state: .value.state})'

# Get all IPv4 addresses by interface
cat router.json | jq '.network.interfaces.parsed | to_entries | map({interface: .key, ipv4: [.value.addresses[] | select(.family == "inet") | .address]})'

# Get simple interface:IP mapping
cat router.json | jq '.network.interfaces.parsed | to_entries | map({(.key): [.value.addresses[] | select(.family == "inet") | .address]}) | add'

# Get only active interfaces with IPs
cat router.json | jq '.network.interfaces.parsed | to_entries | map(select(.value.state == "UP" and (.value.addresses | length > 0))) | map(.key)'

# Get MAC addresses
cat router.json | jq '.network.interfaces.parsed | to_entries | map({interface: .key, mac: .value.mac_address})'

# Get flat list of all IP addresses
cat router.json | jq '.network.interfaces.parsed | [.[].addresses[].address]'

# Get interfaces in specific subnet
cat router.json | jq '.network.interfaces.parsed | to_entries | map(select(.value.addresses[]?.address | startswith("10.159")))'
```

## 4. Iptables Information

```bash
# Check if iptables is available
cat router.json | jq '.firewall.iptables.available'

# List available iptables tables
cat router.json | jq '.firewall.iptables | keys | map(select(. == "filter" or . == "nat" or . == "mangle"))'

# Get all chain names from filter table
cat router.json | jq '.firewall.iptables.filter | map(keys) | add'

# Count rules in each chain
cat router.json | jq '.firewall.iptables.filter | map(to_entries[0]) | map({chain: .key, rules: (.value | length)})'

# Get all chains across all tables
cat router.json | jq '[.firewall.iptables.filter, .firewall.iptables.nat, .firewall.iptables.mangle] | map(map(keys)) | add | add | unique'

# Get rules with specific target (e.g., ACCEPT)
cat router.json | jq '.firewall.iptables.filter | map(to_entries[0]) | map({chain: .key, accept_rules: [.value[] | select(.target == "ACCEPT")]}) | map(select(.accept_rules | length > 0))'

# Get total rule count across all tables
cat router.json | jq '[.firewall.iptables.filter, .firewall.iptables.nat, .firewall.iptables.mangle] | map(map(to_entries[0].value | length)) | add | add'

# Get chain references (custom chains)
cat router.json | jq '.firewall.iptables.chain_references'

# Get rules from specific chain
cat router.json | jq '.firewall.iptables.filter | map(select(has("FORWARD"))) | .[0].FORWARD'

# Get rules with match-set extensions (ipset references)
cat router.json | jq '.firewall.iptables.filter | map(to_entries[0].value) | add | map(select(.extensions.match_sets?))'
```

## 5. Ipset Information

```bash
# Check if ipsets are available
cat router.json | jq '.firewall.ipset.available'

# List all ipset names
cat router.json | jq '.firewall.ipset.lists | map(keys) | add'

# Count total ipsets
cat router.json | jq '.firewall.ipset.lists | map(keys) | add | length'

# Get ipset details with member counts
cat router.json | jq '.firewall.ipset.lists | map(to_entries[0]) | map({name: .key, type: .value.type, members: (.value.members | length)})'

# Get largest ipsets by member count
cat router.json | jq '.firewall.ipset.lists | map(to_entries[0]) | map({name: .key, type: .value.type, members: (.value.members | length)}) | sort_by(.members) | reverse | .[0:10]'

# Get ipsets by type
cat router.json | jq '.firewall.ipset.lists | map(to_entries[0]) | group_by(.value.type) | map({type: .[0].value.type, count: length})'

# Get specific ipset details
cat router.json | jq '.firewall.ipset.lists | map(select(has("RFC1918"))) | .[0].RFC1918'

# Find ipsets containing specific IP
cat router.json | jq '.firewall.ipset.lists | map(to_entries[0]) | map(select(.value.members[] | contains("192.168"))) | map(.key)'

# Get ipset names matching pattern
cat router.json | jq '.firewall.ipset.lists | map(keys) | add | map(select(. | contains("ZIT")))'

# Get empty ipsets
cat router.json | jq '.firewall.ipset.lists | map(to_entries[0]) | map(select(.value.members | length == 0)) | map(.key)'
```

## 6. Combined Queries

```bash
# Get complete network summary
cat router.json | jq '{
  hostname: .metadata.hostname,
  interfaces: (.network.interfaces.parsed | keys | length),
  routing_rules: (.routing.rules | length),
  routing_entries: (.routing.tables | length),
  iptables_chains: ([.firewall.iptables.filter, .firewall.iptables.nat, .firewall.iptables.mangle] | map(map(keys)) | add | add | unique | length),
  ipsets: (.firewall.ipset.lists | map(keys) | add | length)
}'

# Get security-related summary
cat router.json | jq '{
  hostname: .metadata.hostname,
  total_iptables_rules: ([.firewall.iptables.filter, .firewall.iptables.nat, .firewall.iptables.mangle] | map(map(to_entries[0].value | length)) | add | add),
  total_ipset_members: (.firewall.ipset.lists | map(to_entries[0].value.members | length) | add),
  active_interfaces: (.network.interfaces.parsed | to_entries | map(select(.value.state == "UP")) | length)
}'

# Find interfaces, rules, and ipsets for specific subnet
cat router.json | jq --arg subnet "10.159" '{
  interfaces: (.network.interfaces.parsed | to_entries | map(select(.value.addresses[]?.address | startswith($subnet))) | map(.key)),
  routing_rules: (.routing.rules | map(select(.src | startswith($subnet)))),
  ipsets: (.firewall.ipset.lists | map(to_entries[0]) | map(select(.value.members[] | startswith($subnet))) | map(.key))
}'
```

## 7. Processing Multiple Files

```bash
# Get interface names from multiple routers
cat router1.json router2.json | jq '.network.interfaces.parsed | keys' | jq -s 'add | unique'

# Compare iptables rule counts across routers
cat *.json | jq '{hostname: .metadata.hostname, rules: ([.firewall.iptables.filter, .firewall.iptables.nat, .firewall.iptables.mangle] | map(map(to_entries[0].value | length)) | add | add)}' | jq -s 'sort_by(.rules)'

# Get all unique ipset names across routers
cat *.json | jq '.firewall.ipset.lists | map(keys) | add' | jq -s 'add | unique'
```

## Tips

1. Use `jq -r` for raw output (removes quotes from strings)
2. Use `jq -c` for compact output (one line per result)
3. Use `jq -s` to read entire input stream into array (useful for multiple files)
4. Use `--arg` to pass shell variables to jq
5. Combine with other tools: `cat router.json | jq '.interfaces.parsed | keys[]' | wc -l`
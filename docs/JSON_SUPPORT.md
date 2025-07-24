# JSON Support in Traceroute Simulator

This document describes JSON support across the traceroute simulator, including variable management, command output, and data manipulation.

## Variable Manager JSON Functions

The variable manager in `tsimsh` provides comprehensive JSON support for working with structured data.

### Supported Dictionary Methods

| Method | Description | Example |
|--------|-------------|---------|
| `.keys()` | Returns a list of all dictionary keys | `$mydict.keys()` → `["key1", "key2"]` |
| `.values()` | Returns a list of all dictionary values | `$mydict.values()` → `[val1, val2]` |
| `.get("key")` | Gets value for key, returns null if not found | `$mydict.get("key1")` → `value1` |
| `.get('key')` | Gets value for key (single quotes) | `$mydict.get('key1')` → `value1` |
| `.length()` | Returns the length/size of any data type | See table below |

#### Length Method Behavior

The `.length()` method works on all data types, similar to jq:

| Data Type | Behavior | Example |
|-----------|----------|---------|
| Dictionary | Number of keys | `{"a":1,"b":2}.length()` → `2` |
| List/Array | Number of elements | `[1,2,3,4,5].length()` → `5` |
| String | Number of characters | `"hello".length()` → `5` |
| Number | Number of digits (as string) | `12345.length()` → `5` |
| null/None | Always returns 0 | `null.length()` → `0` |
| Boolean | Length of string representation | `true.length()` → `4` |

### Access Patterns

#### Dot Notation
Access dictionary keys using dot notation:
```bash
tsimsh> data='{"name":"router1","ip":"10.1.1.1"}'
tsimsh> echo $data.name
router1
tsimsh> echo $data.ip
10.1.1.1
```

#### Bracket Notation
Access dictionary keys or list indices using brackets:
```bash
# Dictionary access
tsimsh> echo $data['name']
router1
tsimsh> echo $data["ip"]
10.1.1.1

# List access
tsimsh> items='[1,2,3,4,5]'
tsimsh> echo $items[0]
1
tsimsh> echo $items[-1]
5
```

#### Nested Access
Access deeply nested structures:
```bash
tsimsh> config='{"routers":{"hq":{"interfaces":[{"name":"eth0","ip":"10.1.1.1"}]}}}'
tsimsh> echo $config.routers.hq.interfaces[0].name
eth0
tsimsh> echo $config['routers']['hq']['interfaces'][0]['ip']
10.1.1.1
```

### JSON Parsing and Serialization

#### Automatic JSON Parsing
String values that look like JSON are automatically parsed:
```bash
tsimsh> data='{"active":true,"count":42}'
tsimsh> echo $data.active
true
tsimsh> echo $data.count
42
```

#### JSON Serialization
Dictionaries and lists are automatically serialized to JSON when substituted:
```bash
tsimsh> mydict.key1="value1"
tsimsh> mydict.key2="value2"
tsimsh> echo $mydict
{"key1":"value1","key2":"value2"}
```

### Variable Substitution in Access

Use variables for dynamic access:
```bash
tsimsh> index=2
tsimsh> items='["a","b","c","d"]'
tsimsh> echo $items[$index]
c

tsimsh> key="name"
tsimsh> data='{"name":"test","value":123}'
tsimsh> echo $data[$key]
test
```

## Command JSON Output

Many commands support JSON output format using the `-j` or `--json` flag.

### Commands with JSON Support

| Command | Flag | Description |
|---------|------|-------------|
| `trace` | `-j, --json` | Outputs traceroute results in JSON format |
| `network status` | `-j, --json` | Shows network namespace status as JSON |
| `service list` | `-j, --json` | Lists services in JSON format |
| `host list` | `-j, --json` | Lists hosts in JSON format |

### JSON Output Behavior

When using JSON output mode:
- **No informational messages** are printed to stdout
- **Only pure JSON** is output (unless verbose mode is also enabled)
- **Error messages** are formatted as JSON error objects
- **Exit codes** remain consistent for scripting

Example:
```bash
# Without JSON flag - includes informational messages
tsimsh> network status
No namespaces found matching pattern: *

# With JSON flag - only JSON output
tsimsh> network status -j
{"error": "No namespaces found matching pattern: *"}
```

### Combining JSON with Verbose Mode

Verbose messages are suppressed in JSON mode unless verbose is explicitly requested:
```bash
# JSON only - clean output
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -j
{"source": "10.1.1.1", "destination": "10.2.1.1", "hops": [...]}

# JSON with verbose - includes debug info on stderr
tsimsh> trace -s 10.1.1.1 -d 10.2.1.1 -j -v
[stderr] Using controller IP from config: 10.1.2.3
{"source": "10.1.1.1", "destination": "10.2.1.1", "hops": [...]}
```

## Working with JSON Data

### Loading JSON from Files
```bash
tsimsh> data=`cat config.json`
tsimsh> echo $data.version
1.0
```

### Processing JSON Arrays
```bash
tsimsh> routers='["hq-gw","br-gw","dc-gw"]'
tsimsh> echo $routers[0]
hq-gw

# Get array length using built-in length() method
tsimsh> echo $routers.length()
3

# Also works without parentheses
tsimsh> echo $routers.length
3

# Works on nested structures
tsimsh> data='{"items":["a","b","c"],"counts":[1,2,3,4,5]}'
tsimsh> echo $data.items.length()
3
tsimsh> echo $data.counts.length()
5
```

### Building JSON Structures
```bash
# Create empty dictionary
tsimsh> config='{}'

# Add keys
tsimsh> config.hostname="router1"
tsimsh> config.ip="10.1.1.1"
tsimsh> config.ports='[22,80,443]'

# Result
tsimsh> echo $config
{"hostname":"router1","ip":"10.1.1.1","ports":[22,80,443]}
```

## Best Practices

1. **Use JSON output for scripting** - Always use `-j` flag when parsing output programmatically
2. **Check for errors** - JSON error responses have an "error" key
3. **Validate JSON** - Use external tools like `jq` for complex JSON processing
4. **Quote properly** - Use single quotes for JSON strings to avoid shell expansion issues

## Examples

### Extract Interface Information
```bash
tsimsh> status=`network status -j -r hq-gw -f interfaces`
tsimsh> echo $status['hq-gw']['interfaces']['eth0']['addresses']
["10.1.1.1/24", "fe80::1/64"]
```

### Service Discovery
```bash
tsimsh> services=`service list -j`
tsimsh> echo $services[0].name
web-server
tsimsh> echo $services[0].port
80
```

### Error Handling
```bash
tsimsh> result=`trace -s 10.1.1.1 -d 10.99.99.99 -j 2>/dev/null`
tsimsh> if [ "$result.error" != "" ]; then echo "Error: $result.error"; fi
Error: No route to destination
```

## Technical Details

- JSON parsing uses Python's `json.loads()` with automatic type detection
- Serialization uses `json.dumps()` with compact formatting (`separators=(',', ':')`)
- Dictionary and list objects are stored as native Python types
- Method calls (`.keys()`, `.values()`) are evaluated at access time
- Invalid JSON strings are stored as plain strings without parsing
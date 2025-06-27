# Error Handling Migration Guide

This guide explains how to migrate existing code to use the new structured error handling system.

## Overview

The new error handling system provides:
- User-friendly error messages without technical jargon
- Helpful suggestions for resolving issues
- Structured logging with verbosity control
- Type-safe data models
- Consistent error codes for automation

## Key Components

### 1. Exception Hierarchy (`src/core/exceptions.py`)

Replace generic exceptions with specific ones:

```python
# Old approach
raise ValueError(f"Router {name} not found")

# New approach
raise RouterNotFoundError(
    name,
    available_routers=list(self.routers.keys())
)
```

### 2. Data Models (`src/core/models.py`)

Replace dictionaries with type-safe dataclasses:

```python
# Old approach
route = {
    'dst': '10.1.0.0/24',
    'dev': 'eth0',
    'gateway': '10.1.0.254'
}

# New approach
route = Route(
    destination='10.1.0.0/24',
    interface='eth0',
    gateway='10.1.0.254'
)
```

### 3. Structured Logging (`src/core/logging.py`)

Replace print statements with structured logging:

```python
# Old approach
if verbose:
    print(f"Loading router {name}")

# New approach
logger = get_logger(__name__, verbose_level)
logger.info(f"Loading router: {name}", router=name, file_count=count)
```

## Migration Steps

### Step 1: Update Imports

Add the new imports to your modules:

```python
from src.core.exceptions import (
    TracerouteError, ConfigurationError, IPNotFoundError,
    NoRouteError, InvalidIPError, ErrorHandler
)
from src.core.models import Route, RouterMetadata, TraceroutePath
from src.core.logging import get_logger, setup_logging
```

### Step 2: Replace Error Handling

#### File/Directory Errors

```python
# Old
if not os.path.exists(facts_dir):
    raise ValueError(f"No router data found in {facts_dir}")

# New
if not os.path.exists(facts_dir):
    raise FactsDirectoryError(facts_dir)
```

#### IP Validation Errors

```python
# Old
try:
    ipaddress.ip_address(ip)
except ValueError:
    print(f"Error: Invalid IP address - '{ip}' does not appear to be an IPv4 or IPv6 address")
    sys.exit(10)

# New
try:
    ipaddress.ip_address(ip)
except ValueError as e:
    raise InvalidIPError(ip, cause=e)
```

#### Network Errors

```python
# Old
print(f"Error: Source IP {src_ip} is not configured on any router or in any directly connected network")
return None

# New
raise IPNotFoundError(
    src_ip,
    "Source",
    available_networks=self._get_available_networks()
)
```

### Step 3: Update Main Functions

Wrap main functions with error handler:

```python
# Old
def main():
    try:
        # main logic
    except Exception as e:
        print(f"Error: {e}")
        return 1

# New
@ErrorHandler.wrap_main
def main():
    # main logic - exceptions handled automatically
```

### Step 4: Add Verbosity Control

Replace verbose flags with levels:

```python
# Old
def __init__(self, verbose=False):
    self.verbose = verbose

# New
def __init__(self, verbose_level=0):
    self.verbose_level = verbose_level
    self.logger = get_logger(__name__, verbose_level)
```

### Step 5: Update Error Messages

Make error messages user-friendly:

```python
# Old
raise Exception(f"KeyError: 'routes' not found in {file}")

# New
raise RouterDataError(
    router_name=name,
    file_path=file,
    parse_error="Missing routing data",
    details={"missing_field": "routes"}
)
```

## Example: Complete Function Migration

### Before

```python
def load_router(self, router_file):
    try:
        with open(router_file) as f:
            data = json.load(f)
        
        if 'routes' not in data:
            print(f"Error: No routes in {router_file}")
            return None
            
        routes = data['routes']
        return Router(routes)
        
    except FileNotFoundError:
        print(f"Error: File {router_file} not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {router_file}: {e}")
        return None
```

### After

```python
def load_router(self, router_file: Path) -> Router:
    router_name = router_file.stem
    
    try:
        with open(router_file) as f:
            data = json.load(f)
            
        # Validate data
        if 'routing' not in data or 'routes' not in data['routing']:
            raise KeyError("Missing routing data")
            
        # Convert to typed models
        routes = [Route.from_dict(r) for r in data['routing']['routes']]
        metadata = RouterMetadata.from_dict(data.get('metadata', {}))
        
        router = EnhancedRouter(router_name, routes, [], metadata, self.logger)
        
        self.logger.log_router_loading(
            router_name,
            success=True,
            route_count=len(routes)
        )
        
        return router
        
    except FileNotFoundError as e:
        raise RouterDataError(
            router_name,
            str(router_file),
            "File not found",
            cause=e
        )
    except json.JSONDecodeError as e:
        raise RouterDataError(
            router_name,
            str(router_file),
            f"Invalid JSON: {str(e)}",
            cause=e
        )
    except KeyError as e:
        raise RouterDataError(
            router_name,
            str(router_file),
            f"Missing required field: {str(e)}",
            cause=e
        )
```

## Testing Error Handling

### Unit Tests

Test each error condition:

```python
def test_invalid_ip_error(self):
    with self.assertRaises(InvalidIPError) as cm:
        validate_ip("not-an-ip")
    
    error = cm.exception
    self.assertEqual(error.error_code, ErrorCode.INVALID_INPUT)
    self.assertIn("Invalid IP address format", str(error))
```

### Integration Tests

Test command-line error handling:

```python
def test_cli_error_handling(self):
    result = subprocess.run(
        ["python", "simulator.py", "-s", "bad-ip", "-d", "10.1.1.1"],
        capture_output=True,
        text=True
    )
    
    self.assertEqual(result.returncode, ErrorCode.INVALID_INPUT)
    self.assertIn("Error:", result.stderr)
    self.assertIn("Suggestion:", result.stderr)
    self.assertNotIn("Traceback", result.stderr)
```

### Manual Testing

Test different verbosity levels:

```bash
# Basic error (no stack trace)
python simulator.py -s bad-ip -d 10.1.1.1

# Verbose error (with details)
python simulator.py -s bad-ip -d 10.1.1.1 -v

# Debug error (with cause)
python simulator.py -s bad-ip -d 10.1.1.1 -vv

# Trace error (with stack trace)
python simulator.py -s bad-ip -d 10.1.1.1 -vvv
```

## Benefits

1. **Better User Experience**: Users see helpful messages instead of stack traces
2. **Easier Debugging**: Structured logging helps trace issues
3. **Automation Friendly**: Consistent exit codes for scripts
4. **Type Safety**: Catch errors at development time
5. **Maintainability**: Clear error categories and handling

## Gradual Migration

You don't need to migrate everything at once:

1. Start with the most common error paths
2. Add new exceptions as you encounter errors
3. Update logging in performance-critical sections
4. Gradually replace dictionaries with dataclasses

## Compatibility

The new system is designed to coexist with old code:
- Old exceptions are caught and wrapped
- Print statements still work (but should be migrated)
- Dictionary-based data structures are converted as needed
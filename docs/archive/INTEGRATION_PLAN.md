# Integration Plan: Adding Error Handling to Existing Code

## What You Actually Need to Do

### 1. Update the existing `traceroute_simulator.py` imports:

```python
# Add at the top of the file
from .exceptions import (
    FactsDirectoryError, NoRouterDataError, IPNotFoundError,
    NoRouteError, InvalidIPError, RouterDataError, ErrorHandler
)
from .logging import get_logger, setup_logging
```

### 2. Wrap the main function:

```python
# Change this:
def main():
    # existing code

# To this:
@ErrorHandler.wrap_main
def main():
    # existing code
```

### 3. Replace error messages gradually:

```python
# Instead of:
if not os.path.exists(tsim_facts):
    raise ValueError(f"No router data found in {tsim_facts}")

# Use:
if not os.path.exists(tsim_facts):
    raise FactsDirectoryError(tsim_facts)
```

### 4. Replace print statements for errors:

```python
# Instead of:
print(f"Error: Source IP {src_ip} is not configured on any router")
sys.exit(2)

# Use:
raise IPNotFoundError(src_ip, "Source", available_networks=networks)
```

### 5. Add verbosity support:

```python
# In argument parser:
parser.add_argument('-v', '--verbose', action='count', default=0,
                   help='Increase verbosity (-v, -vv, -vvv)')

# Setup logging:
setup_logging(args.verbose)
logger = get_logger(__name__, args.verbose)
```

## Example: Minimal Changes to Start

Here's a minimal change to the existing traceroute_simulator.py to add error handling:

```python
#!/usr/bin/env python3

# ... existing imports ...

# Add new imports
try:
    from .exceptions import (
        FactsDirectoryError, IPNotFoundError, InvalidIPError,
        NoRouteError, ErrorHandler
    )
    from .logging import get_logger, setup_logging
    ERROR_HANDLING_AVAILABLE = True
except ImportError:
    # Fallback for backward compatibility
    ERROR_HANDLING_AVAILABLE = False
    
    class ErrorHandler:
        @staticmethod
        def wrap_main(func):
            return func

# ... rest of existing code ...

# Update main function
@ErrorHandler.wrap_main
def main():
    # ... existing argument parsing ...
    
    # Add verbose counting
    parser.add_argument('-v', '--verbose', action='count', default=0,
                       help='Increase verbosity (-v, -vv, -vvv)')
    
    args = parser.parse_args()
    
    # Setup logging if available
    if ERROR_HANDLING_AVAILABLE:
        setup_logging(args.verbose)
    
    # ... rest of existing main code ...
    
    # Replace specific errors gradually
    try:
        simulator = TracerouteSimulator(facts_dir)
    except ValueError as e:
        if ERROR_HANDLING_AVAILABLE and "No router data found" in str(e):
            raise FactsDirectoryError(facts_dir)
        else:
            raise  # Keep original behavior
```

## What NOT to Do

1. **Don't maintain two separate implementations** (original and v2)
2. **Don't try to replace everything at once**
3. **Don't break existing functionality**

## Incremental Migration Path

1. **Phase 1**: Add imports and wrap main (backward compatible)
2. **Phase 2**: Replace file/directory errors
3. **Phase 3**: Replace IP validation errors  
4. **Phase 4**: Replace routing errors
5. **Phase 5**: Add logging throughout

## Testing During Migration

After each change, run:
```bash
# Test existing functionality still works
make test

# Test new error handling
python3 traceroute_simulator.py -s invalid-ip -d 10.1.1.1
# Should show friendly error, not stack trace
```

## Summary

The v2 file was just a demo. The real work is integrating the error handling components into your existing, production code. This should be done incrementally to maintain stability.
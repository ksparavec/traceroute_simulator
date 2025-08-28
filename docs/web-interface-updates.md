# Web Interface Service Analysis Updates

## Overview
The web interface has been significantly enhanced to support multiple port and protocol combinations for service analysis, allowing users to test connectivity to multiple services in a single operation.

## New Features

### 1. Enhanced Port Specification
Users can now specify multiple ports and protocols using:
- **Comma-separated lists**: `22/tcp,80,443/tcp,53/udp`
- **Port ranges**: `8000-8010/tcp` or `1000-2000`
- **Mixed formats**: `22/tcp,80-90,443/tcp,1000-2000/udp`
- **Protocol-specific**: Each port or range can have its own protocol (`/tcp` or `/udp`)
- **Default protocol**: Unspecified ports use the global default protocol setting

### 2. Dual Input Modes

#### Quick Select Mode (Default)
- User-friendly dropdown with common services
- Shows service names and descriptions from `/etc/services`
- Multi-select capability for testing multiple services at once
- Pre-populated with common services like SSH, HTTP, HTTPS, DNS, databases, etc.

#### Manual Entry Mode (Advanced)
- Free-form text input for maximum flexibility
- Supports full port specification syntax
- Allows custom port ranges and combinations
- Ideal for advanced users and non-standard ports

### 3. Multi-Service Testing
- Each port/protocol combination is tested sequentially
- Individual results are generated for each service
- Progress tracking shows which service is currently being tested
- Comprehensive analysis for each service

### 4. Multi-Page PDF Reports
- Each service gets its own report page
- All pages are combined into a single PDF document
- Clear separation between different service tests
- Maintains all existing report features (diagrams, traces, analysis)

## Implementation Details

### New Components

#### `port_parser.py`
- **Purpose**: Parse and validate port specifications
- **Features**:
  - Handles ranges, comma-separated lists, and protocol specifications
  - Loads service descriptions from `/etc/services`
  - Formats port lists for display
  - Validates input syntax

#### Updated `validator.py`
- **New method**: `validate_port_spec()` for validating complex port specifications
- **Enhanced**: `sanitize_input()` now preserves necessary characters for port specs

#### Updated `executor.py`
- **New method**: `generate_multi_page_pdf()` for combining multiple PDF reports
- **Uses**: PyPDF2 library for PDF merging
- **Fallback**: Returns first PDF if merging fails

### Modified Files

#### `form.html`
- Radio buttons for mode selection (Quick/Manual)
- Multi-select dropdown for common services
- Text input for manual port specification
- Default protocol selector
- Help text with examples

#### `form.js`
- `togglePortMode()`: Switches between input modes
- Preserves user selections in localStorage
- Validates input based on selected mode

#### `style.css`
- Styles for radio groups
- Multi-select dropdown styling
- Help text formatting

#### `main.py`
- Handles both input modes
- Parses port specifications using PortParser
- Loops through all port/protocol combinations
- Generates multi-page PDF reports

## Usage Examples

### Quick Select Mode
1. Select "Quick Select (Common Services)"
2. Choose multiple services from the dropdown (hold Ctrl/Cmd)
3. Click "Run Test"

### Manual Entry Mode
1. Select "Manual Entry (Advanced)"
2. Enter port specification:
   - Single port: `80`
   - With protocol: `22/tcp`
   - Multiple: `22/tcp,80,443/tcp`
   - Range: `8000-8010/udp`
   - Mixed: `22/tcp,80-90,1000-2000/udp`
3. Click "Run Test"

## Testing

A test script `test_port_parser.py` is provided to verify:
- Port specification parsing
- Input validation
- Service description lookup
- Port list formatting

Run with: `python3 web/cgi-bin/test_port_parser.py`

## Dependencies

Added to `requirements.txt`:
- **PyPDF2**: For merging individual PDF reports

## Benefits

1. **Efficiency**: Test multiple services in one operation
2. **Flexibility**: Support for any port combination
3. **User-Friendly**: Dual modes cater to both beginners and experts
4. **Comprehensive**: Each service gets full analysis
5. **Professional**: Combined PDF report for documentation

## Backward Compatibility

The update maintains backward compatibility:
- Existing single-port tests continue to work
- Old form data is migrated to new format
- API remains consistent for programmatic access

## Future Enhancements

Potential improvements for future versions:
1. Parallel service testing for faster results
2. Service-specific test customization
3. Export to other formats (JSON, CSV)
4. Service dependency mapping
5. Historical comparison of service availability
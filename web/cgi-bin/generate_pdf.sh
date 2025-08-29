#!/bin/bash
# Generic PDF generation script that accepts parameters

# Get start time for timing
START_TIME=$(python3 -B -u -c "import time; print(time.time())")
LAST_TIME=$START_TIME
RUN_ID="unknown"

# Function to log timing with duration
log_timing() {
    local checkpoint="$1"
    local details="${2:-}"
    local current_time=$(python3 -B -u -c "import time; print(time.time())")
    local duration=$(python3 -B -u -c "import sys; print(f'{float(sys.argv[1]) - float(sys.argv[2]):7.2f}')" "$current_time" "$LAST_TIME")
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S.%3N")
    local log_file="/var/www/traceroute-web/logs/timings.log"
    
    # Update last time
    LAST_TIME=$current_time
    
    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$log_file")" 2>/dev/null || true
    
    # Log entry with duration
    echo "[$timestamp] [$RUN_ID] ${duration}s | PDF_GEN_${checkpoint} | $details" >> "$log_file" 2>/dev/null || true
}

# Parse query string parameters
log_timing "PARSE_START"
if [ "$REQUEST_METHOD" = "GET" ]; then
    # Parse QUERY_STRING
    IFS='&' read -ra PARAMS <<< "$QUERY_STRING"
    for param in "${PARAMS[@]}"; do
        IFS='=' read -ra KV <<< "$param"
        case ${KV[0]} in
            trace)
                TRACE_FILE=$(echo "${KV[1]}" | sed 's/%2F/\//g' | sed 's/%20/ /g')
                ;;
            results)
                RESULTS_FILE=$(echo "${KV[1]}" | sed 's/%2F/\//g' | sed 's/%20/ /g')
                ;;
            output)
                OUTPUT_FILE=$(echo "${KV[1]}" | sed 's/%2F/\//g' | sed 's/%20/ /g')
                # Extract run ID from output filename (handles both _report.pdf and _<port>_<protocol>.pdf)
                if [[ "$OUTPUT_FILE" =~ ([a-f0-9-]+)(_report\.pdf|_[0-9]+_[a-z]+\.pdf) ]]; then
                    RUN_ID="${BASH_REMATCH[1]}"
                fi
                ;;
            service)
                SERVICE_INFO=$(echo "${KV[1]}" | sed 's/%2F/\//g' | sed 's/%20/ /g')
                ;;
        esac
    done
fi
log_timing "parse_params" "trace=$TRACE_FILE results=$RESULTS_FILE output=$OUTPUT_FILE"

# Validate parameters
if [ -z "$TRACE_FILE" ] || [ -z "$RESULTS_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    log_timing "validate_error" "Missing parameters"
    echo "Content-Type: text/plain"
    echo ""
    echo "Error: Missing required parameters (trace, results, output)"
    exit 1
fi
log_timing "validate_params" "Parameters validated"

# CGI header
echo "Content-Type: application/pdf"
echo "Content-Disposition: attachment; filename=\"$(basename "$OUTPUT_FILE")\""
echo ""

# Get venv_path from config.json
CONFIG_FILE="/var/www/traceroute-web/conf/config.json"
if [ -f "$CONFIG_FILE" ]; then
    VENV_PATH=$(python3 -B -u -c "import json; config = json.load(open('$CONFIG_FILE')); print(config.get('venv_path', ''))")
else
    echo "Error: config.json not found" >&2
    exit 1
fi

# Source the virtual environment
if [ -z "$VENV_PATH" ]; then
    echo "Error: venv_path not configured in config.json" >&2
    exit 1
fi

if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    log_timing "venv_activate" "Virtual environment activated from $VENV_PATH"
else
    echo "Error: Virtual environment not found at $VENV_PATH" >&2
    exit 1
fi

# Run Python to generate PDF
python3 -B -u << EOF
import sys
import os
import subprocess
import time
from datetime import datetime

# Python doesn't need separate timing - handled by bash

# Set matplotlib backend and config directory
os.environ['MPLBACKEND'] = 'Agg'
os.environ['DISPLAY'] = ''
os.environ['MPLCONFIGDIR'] = '/var/www/traceroute-web/matplotlib_cache'
# Create the cache directory if it doesn't exist
os.makedirs('/var/www/traceroute-web/matplotlib_cache', exist_ok=True, mode=0o775)

# Files from parameters
trace_file = "${TRACE_FILE}"
results_file = "${RESULTS_FILE}"
output_file = "${OUTPUT_FILE}"
service_info = "${SERVICE_INFO}"

# Run visualization
script_path = "/var/www/traceroute-web/scripts/visualize_reachability.py"
cmd = [sys.executable, "-B", "-u", script_path,
       "--trace", trace_file,
       "--results", results_file,
       "--output", output_file]

# Add service info if provided
if service_info:
    cmd.extend(["--service", service_info])

result = subprocess.run(cmd, capture_output=True, text=True)

# Log the command and result for debugging
os.makedirs('/var/www/traceroute-web/logs', exist_ok=True, mode=0o775)
with open('/var/www/traceroute-web/logs/pdf_debug.log', 'a') as debug:
    debug.write(f"Command: {' '.join(cmd)}\n")
    debug.write(f"Return code: {result.returncode}\n")
    debug.write(f"Stdout: {result.stdout}\n")
    debug.write(f"Stderr: {result.stderr}\n")
    debug.write(f"Output file exists: {os.path.exists(output_file)}\n")
    if os.path.exists(output_file):
        debug.write(f"Output file size: {os.path.getsize(output_file)}\n")
    debug.write("-" * 50 + "\n")

if result.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 0:
    # Output the PDF to stdout
    with open(output_file, 'rb') as f:
        sys.stdout.buffer.write(f.read())
else:
    # Error - but we already sent PDF headers, so send an empty PDF or error text
    error_msg = f"Error generating PDF: {result.stderr if result.stderr else result.stdout}"
    # Since we already sent PDF headers, we can't change them
    # Best we can do is output the error to stderr for logging
    print(error_msg, file=sys.stderr)
    sys.exit(1)
EOF

log_timing "visualize_reachability.py" "PDF generation complete"

# Log total time
total_time=$(python3 -B -u -c "import sys; print(f'{float(sys.argv[1]) - float(sys.argv[2]):7.2f}')" "$(python3 -B -u -c 'import time; print(time.time())')" "$START_TIME")
log_timing "TOTAL" "Total time: ${total_time}s"
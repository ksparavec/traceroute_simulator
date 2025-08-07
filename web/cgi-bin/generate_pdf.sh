#!/bin/bash
# Generic PDF generation script that accepts parameters

# Get start time for timing
START_TIME=$(python3 -B -u -c "import time; print(time.time())")
RUN_ID="unknown"

# Function to log timing
log_timing() {
    local checkpoint="$1"
    local details="${2:-}"
    local current_time=$(python3 -B -u -c "import time; print(time.time())")
    local elapsed=$(python3 -B -u -c "import sys; print(f'{float(sys.argv[1]) - float(sys.argv[2]):7.2f}')" "$current_time" "$START_TIME")
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S.%3N")
    local log_file="/var/www/traceroute-web/logs/timings.log"
    
    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$log_file")" 2>/dev/null || true
    
    # Log entry
    echo "[$timestamp] [$RUN_ID] ${elapsed}s | PDF_GEN_${checkpoint} | $details" >> "$log_file" 2>/dev/null || true
}

log_timing "START" "generate_pdf.sh"

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
                # Extract run ID from output filename
                if [[ "$OUTPUT_FILE" =~ ([a-f0-9-]+)_report\.pdf ]]; then
                    RUN_ID="${BASH_REMATCH[1]}"
                fi
                ;;
        esac
    done
fi
log_timing "PARSE_END" "trace=$TRACE_FILE results=$RESULTS_FILE output=$OUTPUT_FILE"

# Validate parameters
log_timing "VALIDATE_START"
if [ -z "$TRACE_FILE" ] || [ -z "$RESULTS_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    log_timing "VALIDATE_ERROR" "Missing parameters"
    echo "Content-Type: text/plain"
    echo ""
    echo "Error: Missing required parameters (trace, results, output)"
    exit 1
fi
log_timing "VALIDATE_END"

# CGI header
echo "Content-Type: application/pdf"
echo "Content-Disposition: attachment; filename=\"$(basename "$OUTPUT_FILE")\""
echo ""

# Source the virtual environment
log_timing "VENV_ACTIVATE_START"
source /home/fxsparavec/tsim/bin/activate
log_timing "VENV_ACTIVATE_END"

# Run Python to generate PDF
log_timing "PYTHON_START"
/home/fxsparavec/tsim/bin/python -B -u << EOF
import sys
import os
import subprocess
import time
from datetime import datetime

# Timing setup
script_start = time.time()
run_id = "${RUN_ID}"

def log_timing(checkpoint, details=""):
    elapsed = time.time() - script_start
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_file = "/var/www/traceroute-web/logs/timings.log"
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] [{run_id}] {elapsed:7.2f}s | PDF_PY_{checkpoint} | {details}\\n")

log_timing("START", "Python PDF generation")

# Set matplotlib backend and config directory
log_timing("MATPLOTLIB_CONFIG_START")
os.environ['MPLBACKEND'] = 'Agg'
os.environ['DISPLAY'] = ''
os.environ['MPLCONFIGDIR'] = '/var/www/traceroute-web/matplotlib_cache'
# Create the cache directory if it doesn't exist
os.makedirs('/var/www/traceroute-web/matplotlib_cache', exist_ok=True)
log_timing("MATPLOTLIB_CONFIG_END")

# Files from parameters
trace_file = "${TRACE_FILE}"
results_file = "${RESULTS_FILE}"
output_file = "${OUTPUT_FILE}"

# Run visualization
log_timing("VISUALIZE_START", f"trace={os.path.basename(trace_file)} results={os.path.basename(results_file)}")
script_path = "/var/www/traceroute-web/scripts/visualize_reachability.py"
cmd = [sys.executable, "-B", "-u", script_path,
       "--trace", trace_file,
       "--results", results_file,
       "--output", output_file]

visualize_start = time.time()
result = subprocess.run(cmd, capture_output=True, text=True)
visualize_duration = time.time() - visualize_start
log_timing("VISUALIZE_END", f"duration={visualize_duration:.2f}s, rc={result.returncode}")

# Log the command and result for debugging
os.makedirs('/var/www/traceroute-web/logs', exist_ok=True)
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
    log_timing("OUTPUT_START", f"size={os.path.getsize(output_file)} bytes")
    with open(output_file, 'rb') as f:
        sys.stdout.buffer.write(f.read())
    log_timing("OUTPUT_END")
else:
    # Error - but we already sent PDF headers, so send an empty PDF or error text
    error_msg = f"Error generating PDF: {result.stderr if result.stderr else result.stdout}"
    log_timing("ERROR", error_msg[:100])
    # Since we already sent PDF headers, we can't change them
    # Best we can do is output the error to stderr for logging
    print(error_msg, file=sys.stderr)
    sys.exit(1)

log_timing("END", "Python script complete")
EOF

log_timing "PYTHON_END"
log_timing "END" "generate_pdf.sh complete"
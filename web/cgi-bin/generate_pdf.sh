#!/bin/bash
# Generic PDF generation script that accepts parameters

# Parse query string parameters
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
                ;;
        esac
    done
fi

# Validate parameters
if [ -z "$TRACE_FILE" ] || [ -z "$RESULTS_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "Content-Type: text/plain"
    echo ""
    echo "Error: Missing required parameters (trace, results, output)"
    exit 1
fi

# CGI header
echo "Content-Type: application/pdf"
echo "Content-Disposition: attachment; filename=\"$(basename "$OUTPUT_FILE")\""
echo ""

# Source the virtual environment
source /home/fxsparavec/tsim/bin/activate

# Run Python to generate PDF
/home/fxsparavec/tsim/bin/python -B -u << EOF
import sys
import os
import subprocess

# Set matplotlib backend
os.environ['MPLBACKEND'] = 'Agg'
os.environ['DISPLAY'] = ''

# Files from parameters
trace_file = "${TRACE_FILE}"
results_file = "${RESULTS_FILE}"
output_file = "${OUTPUT_FILE}"

# Run visualization
script_path = "/var/www/traceroute-web/scripts/visualize_reachability.py"
cmd = [sys.executable, "-B", "-u", script_path,
       "--trace", trace_file,
       "--results", results_file,
       "--output", output_file]

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode == 0 and os.path.exists(output_file):
    # Output the PDF to stdout
    with open(output_file, 'rb') as f:
        sys.stdout.buffer.write(f.read())
else:
    # Error - switch to text response
    print("Content-Type: text/plain", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"Error generating PDF: {result.stderr}", file=sys.stderr)
    sys.exit(1)
EOF
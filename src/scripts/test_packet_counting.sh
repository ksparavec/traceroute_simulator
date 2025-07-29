#!/usr/bin/env bash
#
# Quick test script for packet counting analysis
# Tests the packet counting script with minimal overhead
#

set -u

# Parse command line arguments
ROUTER="${1:-}"
SOURCE_IP="${2:-}"
DEST_IP="${3:-}"
DEST_PORT="${4:-}"
PROTOCOL="${5:-tcp}"
MODE="${6:-blocking}"  # blocking or allowing

if [[ -z "$ROUTER" ]] || [[ -z "$SOURCE_IP" ]] || [[ -z "$DEST_IP" ]] || [[ -z "$DEST_PORT" ]]; then
    echo "Usage: $0 ROUTER SOURCE_IP DEST_IP DEST_PORT [PROTOCOL] [MODE]"
    echo "Example: $0 hq-gw 10.1.1.100 10.3.20.100 80 tcp blocking"
    echo "Example: $0 hq-gw 10.1.1.100 10.3.20.100 80 tcp allowing"
    exit 1
fi

# Function to execute tsimsh commands
tsimsh_exec() {
    local command="$1"
    echo ">>> $command" >&2
    echo "$command" | tsimsh -q 2>&1 | grep -v '^ℹ' || true
}

echo "=== Testing packet counting for router: $ROUTER ===" >&2
echo "Source: $SOURCE_IP -> Destination: $DEST_IP:$DEST_PORT ($PROTOCOL)" >&2
echo "Analysis mode: $MODE" >&2

# Step 1: Get initial packet counts
echo -e "\n[Step 1] Getting initial iptables packet counts..." >&2
BEFORE_FILE=$(mktemp)
tsimsh_exec "network status --limit $ROUTER iptables --json" > "$BEFORE_FILE"

# Step 2: Show initial state (optional debug)
if [[ "${DEBUG:-0}" == "1" ]]; then
    echo -e "\nInitial iptables state:" >&2
    cat "$BEFORE_FILE" | jq '.' >&2
fi

# Step 3: Execute service test
echo -e "\n[Step 2] Executing service test..." >&2
SERVICE_CMD="service test --source $SOURCE_IP --destination ${DEST_IP}:${DEST_PORT} --protocol $PROTOCOL --json"
echo "Exact command: $SERVICE_CMD" >&2
SERVICE_RESULT=$(tsimsh_exec "$SERVICE_CMD")
echo "Service test result:" >&2
echo "$SERVICE_RESULT" | jq '.' >&2
echo "Summary only:" >&2
echo "$SERVICE_RESULT" | jq -r '.summary' >&2
echo "Individual tests:" >&2
echo "$SERVICE_RESULT" | jq -r '.tests[] | "  Router: \(.via_router) - Status: \(.status)"' >&2

# Extract result for THIS router only
echo -e "\nFiltering for router: $ROUTER" >&2
ROUTER_TEST_RESULT=$(echo "$SERVICE_RESULT" | jq -r '.tests[] | select(.via_router == "'$ROUTER'") | .status' 2>/dev/null)
echo "This router's test result: $ROUTER_TEST_RESULT" >&2

# Determine the correct analysis mode based on THIS router's result
if [[ "$ROUTER_TEST_RESULT" == "OK" ]]; then
    if [[ "$MODE" != "allowing" ]]; then
        echo "Note: Service succeeded through this router. Switching to 'allowing' mode to see which rules allowed it." >&2
        MODE="allowing"
    fi
elif [[ "$ROUTER_TEST_RESULT" == "FAIL" ]]; then
    if [[ "$MODE" != "blocking" ]]; then
        echo "Note: Service failed through this router. Switching to 'blocking' mode to see which rules blocked it." >&2
        MODE="blocking"
    fi
else
    echo "Warning: No test result found for router $ROUTER" >&2
fi

# Step 4: Get final packet counts
echo -e "\n[Step 3] Getting final iptables packet counts..." >&2
AFTER_FILE=$(mktemp)
tsimsh_exec "network status --limit $ROUTER iptables --json" > "$AFTER_FILE"

# Step 5: Run packet counting analysis
echo -e "\n[Step 4] Running packet count analysis..." >&2
echo "Analysis mode: $MODE (based on this router's test result)" >&2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add extra debugging - check specific chain
if [[ "${DEBUG_CHAIN:-}" != "" ]]; then
    echo -e "\nChecking $DEBUG_CHAIN chain in before/after data:" >&2
    echo "BEFORE:" >&2
    cat "$BEFORE_FILE" | jq ".\"$ROUTER\".iptables.filter.chains.\"$DEBUG_CHAIN\".rules[0:3]" 2>/dev/null || echo "Chain not found" >&2
    echo "AFTER:" >&2
    cat "$AFTER_FILE" | jq ".\"$ROUTER\".iptables.filter.chains.\"$DEBUG_CHAIN\".rules[0:3]" 2>/dev/null || echo "Chain not found" >&2
fi

ANALYSIS_RESULT=$("$SCRIPT_DIR/analyze_packet_counts.py" "$ROUTER" "$BEFORE_FILE" "$AFTER_FILE" -m "$MODE" -v 2>&1)

echo -e "\n[Step 5] Analysis result:" >&2
# Extract just the JSON output (last line that's valid JSON)
JSON_RESULT=$(echo "$ANALYSIS_RESULT" | tac | while read -r line; do
    if echo "$line" | jq . >/dev/null 2>&1; then
        echo "$line"
        break
    fi
done | tac)

if [[ -n "$JSON_RESULT" ]]; then
    echo "$JSON_RESULT" | jq '.'
else
    echo "No valid JSON result from analysis" >&2
    echo "Full output:" >&2
    echo "$ANALYSIS_RESULT" >&2
fi

# Cleanup
rm -f "$BEFORE_FILE" "$AFTER_FILE"

echo -e "\n=== Test complete ===" >&2

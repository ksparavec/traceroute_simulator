#!/bin/bash
#
# Master test runner for all parallel job integration scenarios
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_SCRIPT="${SCRIPT_DIR}/test_parallel_jobs.py"
CONFIG_DIR="${SCRIPT_DIR}/configs"
OUTPUT_DIR="${SCRIPT_DIR}/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="${OUTPUT_DIR}/${TIMESTAMP}"

# Default values (can be overridden by environment or command line)
BASE_URL="${TSIM_BASE_URL:-http://localhost/tsim}"
USERNAME="${TSIM_USERNAME:-admin}"
PASSWORD="${TSIM_PASSWORD:-}"
TIMEOUT="${TSIM_TIMEOUT:-600}"

# Parse command line arguments
SEQUENTIAL=""
CHECK_MODE=""
INSECURE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --sequential)
            SEQUENTIAL="--sequential"
            shift
            ;;
        --check)
            CHECK_MODE="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --username)
            USERNAME="$2"
            shift 2
            ;;
        --password)
            PASSWORD="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --insecure|-k)
            INSECURE="--insecure"
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --sequential         Submit jobs sequentially instead of parallel"
            echo "  --check DIR          Check mode: compare with expected results"
            echo "  --base-url URL       Base URL for TSIM API (default: http://localhost/tsim)"
            echo "  --username USER      Authentication username"
            echo "  --password PASS      Authentication password"
            echo "  --timeout SECONDS    Timeout per job (default: 600)"
            echo "  --insecure, -k       Allow insecure SSL connections"
            echo "  --help               Show this help"
            echo ""
            echo "Environment variables:"
            echo "  TSIM_BASE_URL        Base URL (overridden by --base-url)"
            echo "  TSIM_USERNAME        Username (overridden by --username)"
            echo "  TSIM_PASSWORD        Password (overridden by --password)"
            echo "  TSIM_TIMEOUT         Timeout (overridden by --timeout)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$PASSWORD" ]]; then
    echo "ERROR: Password required (use --password or TSIM_PASSWORD)"
    exit 1
fi

# Create output directory
mkdir -p "$RUN_DIR"

# Define scenarios
declare -a SCENARIOS=(
    "01_single_detailed"
    "02_multiple_detailed_disjoint"
    "03_multiple_detailed_overlapping"
    "04_single_quick"
    "05_multiple_quick"
    "06_detailed_quick_disjoint"
    "07_detailed_quick_overlapping"
    "08_detailed_multiple_quick_disjoint"
    "09_detailed_multiple_quick_overlapping"
    "10_multiple_detailed_multiple_quick_disjoint"
    "11_crown_test_overlapping"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Summary tracking
TOTAL_SCENARIOS=${#SCENARIOS[@]}
PASSED_SCENARIOS=0
FAILED_SCENARIOS=0
declare -a FAILED_SCENARIO_NAMES

echo ""
echo "========================================================================"
echo "  TSIM Parallel Job Integration Test Suite"
echo "========================================================================"
echo "  Timestamp:    $TIMESTAMP"
echo "  Output:       $RUN_DIR"
echo "  Base URL:     $BASE_URL"
echo "  Username:     $USERNAME"
echo "  Timeout:      ${TIMEOUT}s"
echo "  Mode:         $([ -n "$SEQUENTIAL" ] && echo "Sequential" || echo "Parallel")"
if [[ -n "$CHECK_MODE" ]]; then
    echo "  Check Mode:   $CHECK_MODE"
fi
echo "========================================================================"
echo ""

# Start timer
START_TIME=$(date +%s)

# Run each scenario
for scenario in "${SCENARIOS[@]}"; do
    config_file="${CONFIG_DIR}/${scenario}.conf"

    if [[ ! -f "$config_file" ]]; then
        echo -e "${YELLOW}WARNING: Config file not found: $config_file (skipping)${NC}"
        continue
    fi

    echo -e "${BLUE}Running scenario: ${scenario}${NC}"
    echo "Config: $config_file"

    # Build command
    cmd=(
        python3 "$TEST_SCRIPT"
        --config "$config_file"
        --scenario "$scenario"
        --output-dir "$RUN_DIR"
        --base-url "$BASE_URL"
        --username "$USERNAME"
        --password "$PASSWORD"
        --timeout "$TIMEOUT"
    )

    if [[ -n "$SEQUENTIAL" ]]; then
        cmd+=("$SEQUENTIAL")
    fi

    if [[ -n "$INSECURE" ]]; then
        cmd+=("$INSECURE")
    fi

    if [[ -n "$CHECK_MODE" ]]; then
        cmd+=(--check "${CHECK_MODE}/${scenario}")
    fi

    # Run scenario
    if "${cmd[@]}"; then
        echo -e "${GREEN}✓ Scenario ${scenario} PASSED${NC}"
        ((PASSED_SCENARIOS++))
    else
        echo -e "${RED}✗ Scenario ${scenario} FAILED${NC}"
        ((FAILED_SCENARIOS++))
        FAILED_SCENARIO_NAMES+=("$scenario")
    fi

    echo ""
done

# End timer
END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

# Generate summary report
SUMMARY_FILE="${RUN_DIR}/summary.json"
cat > "$SUMMARY_FILE" <<EOF
{
  "test_run": {
    "timestamp": "$TIMESTAMP",
    "start_time": $START_TIME,
    "end_time": $END_TIME,
    "duration_seconds": $TOTAL_TIME,
    "output_directory": "$RUN_DIR"
  },
  "configuration": {
    "base_url": "$BASE_URL",
    "username": "$USERNAME",
    "timeout": $TIMEOUT,
    "sequential": $([ -n "$SEQUENTIAL" ] && echo "true" || echo "false"),
    "check_mode": $([ -n "$CHECK_MODE" ] && echo "\"$CHECK_MODE\"" || echo "null")
  },
  "results": {
    "total_scenarios": $TOTAL_SCENARIOS,
    "passed": $PASSED_SCENARIOS,
    "failed": $FAILED_SCENARIOS,
    "failed_scenarios": [
$(IFS=,; printf '      "%s"\n' "${FAILED_SCENARIO_NAMES[@]}" | sed '$ s/,$//')
    ]
  }
}
EOF

# Print summary
echo ""
echo "========================================================================"
echo "  TEST SUITE SUMMARY"
echo "========================================================================"
echo "  Total Time:        ${TOTAL_TIME}s ($(date -d@${TOTAL_TIME} -u +%H:%M:%S))"
echo "  Total Scenarios:   $TOTAL_SCENARIOS"
echo -e "  ${GREEN}Passed:${NC}            $PASSED_SCENARIOS"
echo -e "  ${RED}Failed:${NC}            $FAILED_SCENARIOS"
echo ""

if [[ $FAILED_SCENARIOS -gt 0 ]]; then
    echo -e "${RED}Failed scenarios:${NC}"
    for scenario in "${FAILED_SCENARIO_NAMES[@]}"; do
        echo "  - $scenario"
    done
    echo ""
fi

echo "  Results saved to: $RUN_DIR"
echo "  Summary JSON:     $SUMMARY_FILE"
echo "========================================================================"
echo ""

# Exit with appropriate code
if [[ $FAILED_SCENARIOS -gt 0 ]]; then
    exit 1
else
    exit 0
fi

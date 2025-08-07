#!/usr/bin/env bash
#
# Network Reachability Testing Script
# Tests network service reachability using tsimsh commands
# Outputs comprehensive JSON report with all test results
#

set -eo pipefail

# Script version
readonly VERSION="1.0.0"

# Script directory
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Global variables
declare -A STEP_TIMERS
declare -i STEP_COUNTER=0
declare SOURCE_HOST_ADDED=false
declare DEST_HOST_ADDED=false
declare SERVICE_STARTED=false
declare TRACE_FILE=""
declare INTERACTIVE_MODE=false
declare TSIMSH_VERBOSE=""
# Track hosts we create for cleanup
declare -a CREATED_HOSTS=()

# Get precise start time at script beginning
SCRIPT_START_TIME=$(python3 -B -u -c "import time; print(time.time())")

# Function to log timing to file
log_timing() {
    local checkpoint="$1"
    local details="${2:-}"
    local current_time=$(python3 -B -u -c "import time; print(time.time())")
    local elapsed=$(python3 -B -u -c "import sys; print(f'{float(sys.argv[1]) - float(sys.argv[2]):7.2f}')" "$current_time" "$SCRIPT_START_TIME")
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S.%3N")
    local log_file="/var/www/traceroute-web/logs/timings.log"
    
    # Create log directory if it doesn't exist
    mkdir -p "$(dirname "$log_file")" 2>/dev/null || true
    
    # Log entry format: [timestamp] [session] elapsed_time | checkpoint | details
    local session_id="${RUN_ID:-unknown}"
    local log_entry="[$timestamp] [$session_id] ${elapsed}s | REACHABILITY_${checkpoint}"
    [[ -n "$details" ]] && log_entry="$log_entry | $details"
    
    echo "$log_entry" >> "$log_file" 2>/dev/null || true
}

# Input parameters
SOURCE_IP=""
SOURCE_PORT=""
DEST_IP=""
DEST_PORT=""
PROTOCOL="tcp"

# Temporary files for packet analysis
TEMP_DIR=$(mktemp -d)
readonly TEMP_DIR

# JSON result accumulator
declare -A JSON_RESULTS

# Function to get current timestamp
get_timestamp() {
    date +%s.%N
}

# Function to get elapsed time since script start
get_elapsed_time() {
    local current_time=$(python3 -B -u -c "import time; print(time.time())")
    local elapsed=$(echo "scale=2; $current_time - $SCRIPT_START_TIME" | bc)
    printf "%5.2f" "$elapsed"
}

# Function to format duration
format_duration() {
    local duration=$1
    printf "%.3f" "$duration"
}

# Function to start step timer
start_step() {
    local step_name="$1"
    ((STEP_COUNTER++))
    STEP_TIMERS["${STEP_COUNTER}_name"]="$step_name"
    STEP_TIMERS["${STEP_COUNTER}_start"]=$(get_timestamp)
}

# Function to end step timer and store result
end_step() {
    local result="${1:-}"
    local key="${STEP_COUNTER}_start"
    local start_time="${STEP_TIMERS[$key]}"
    local end_time=$(get_timestamp)
    local duration=$(echo "$end_time - $start_time" | bc)
    
    STEP_TIMERS["${STEP_COUNTER}_duration"]=$(format_duration "$duration")
    STEP_TIMERS["${STEP_COUNTER}_result"]="$result"
}

# Function to execute tsimsh commands
tsimsh_exec() {
    local command="$1"
    local capture_output="${2:-false}"
    
    # Add verbose flags to the command if set
    if [[ -n "$TSIMSH_VERBOSE" ]]; then
        command="$command $TSIMSH_VERBOSE"
    fi
    
    # Debug: print command to stderr with timing
    echo "$(get_elapsed_time) tsimsh: $command" >&2
    
    if [[ "$capture_output" == "true" ]]; then
        # Capture stdout directly - no filtering needed since JSON output is clean
        local output
        # Don't redirect stderr to stdout - keep them separate
        output=$(echo "$command" | tsimsh -q)
        local exit_code=$?
        echo "$output"
        return $exit_code
    else
        # Even when not capturing for return, capture for debug logging
        local output
        local error_output
        output=$(echo "$command" | tsimsh -q 2>&1)
        local exit_code=$?
        
        # If verbose mode is on or command failed, log the output
        if [[ -n "$TSIMSH_VERBOSE" ]] || [[ $exit_code -ne 0 ]]; then
            echo "  Output: $output" >&2
        fi
        
        return $exit_code
    fi
}

# Function to clean up resources
cleanup() {
    # Always run cleanup
    start_step "cleanup"
    
    # Stop service first
    if [[ "$SERVICE_STARTED" == "true" ]]; then
        tsimsh_exec "service stop --ip ${DEST_IP} --port ${DEST_PORT} --protocol ${PROTOCOL}" false || true
    fi
    
    # Remove hosts we created
    if [[ ${#CREATED_HOSTS[@]} -gt 0 ]]; then
        for host in "${CREATED_HOSTS[@]}"; do
            tsimsh_exec "host remove --name ${host} --force" false || true
        done
    fi
    
    end_step "completed"
    
    # Clean up temporary directory
    rm -rf "$TEMP_DIR"
}

# Error handler function
error_handler() {
    local exit_code=$?
    local line_no=$1
    if [[ $exit_code -ne 0 ]]; then
        echo "Error occurred at line $line_no with exit code $exit_code" >&2
    fi
    return $exit_code
}

# Set up cleanup trap for all exit scenarios
trap cleanup EXIT INT TERM HUP
trap 'error_handler $LINENO' ERR

# Function to display usage
usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Options:
    -s, --source IP           Source IP address (required for live trace)
    -p, --source-port PORT    Source port (optional)
    -d, --destination IP      Destination IP address (required for live trace)
    -P, --dest-port PORT      Destination port (mandatory)
    -t, --protocol PROTO      Protocol: tcp or udp (default: tcp)
    -f, --trace-file FILE     Use trace file instead of live trace (extracts IPs from file)
    -i, --interactive         Interactive mode (human-readable output)
    -h, --help                Display this help message
    -v, --version             Display version information
    -V, --verbose             Verbose mode for tsimsh commands (can be used multiple times)

Examples:
    Live trace:
        $(basename "$0") -s 10.1.1.100 -d 10.3.20.100 -P 80
        $(basename "$0") -s 10.1.1.100 -d 10.3.20.100 -P 80 -t tcp
    
    Using trace file:
        $(basename "$0") -f trace_example.json -P 80
        $(basename "$0") -f trace_example.json -P 80 -t tcp

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -s|--source)
                SOURCE_IP="$2"
                shift 2
                ;;
            -p|--source-port)
                SOURCE_PORT="$2"
                shift 2
                ;;
            -d|--destination)
                DEST_IP="$2"
                shift 2
                ;;
            -P|--dest-port)
                DEST_PORT="$2"
                shift 2
                ;;
            -t|--protocol)
                PROTOCOL="$2"
                shift 2
                ;;
            -f|--trace-file)
                TRACE_FILE="$2"
                shift 2
                ;;
            -i|--interactive)
                INTERACTIVE_MODE=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -v|--version)
                echo "Network Reachability Test v${VERSION}"
                exit 0
                ;;
            -V|--verbose)
                TSIMSH_VERBOSE="${TSIMSH_VERBOSE} -v"
                shift
                ;;
            *)
                echo "Error: Unknown option $1" >&2
                usage >&2
                exit 1
                ;;
        esac
    done
}

# Validate input parameters
validate_params() {
    if [[ -n "$TRACE_FILE" ]]; then
        # When using trace file, we'll extract IPs from it
        if [[ ! -f "$TRACE_FILE" ]]; then
            echo "Error: Trace file not found: $TRACE_FILE" >&2
            exit 1
        fi
        
        # Extract source and destination IPs from trace file
        SOURCE_IP=$(jq -r '.source' "$TRACE_FILE" 2>/dev/null)
        DEST_IP=$(jq -r '.destination' "$TRACE_FILE" 2>/dev/null)
        
        if [[ -z "$SOURCE_IP" || "$SOURCE_IP" == "null" ]]; then
            echo "Error: Could not extract source IP from trace file" >&2
            exit 1
        fi
        
        if [[ -z "$DEST_IP" || "$DEST_IP" == "null" ]]; then
            echo "Error: Could not extract destination IP from trace file" >&2
            exit 1
        fi
    else
        # Live trace mode - source and destination IPs are required
        if [[ -z "$SOURCE_IP" ]]; then
            echo "Error: Source IP is required for live trace" >&2
            usage >&2
            exit 1
        fi
        
        if [[ -z "$DEST_IP" ]]; then
            echo "Error: Destination IP is required for live trace" >&2
            usage >&2
            exit 1
        fi
    fi
    
    if [[ -z "$DEST_PORT" ]]; then
        echo "Error: Destination port is required" >&2
        usage >&2
        exit 1
    fi
    
    if [[ "$PROTOCOL" != "tcp" && "$PROTOCOL" != "udp" ]]; then
        echo "Error: Protocol must be tcp or udp" >&2
        usage >&2
        exit 1
    fi
}

# Function to extract routers from trace path
extract_routers_from_trace() {
    local trace_json="$1"
    echo "$trace_json" | jq -r '.path[] | select(.is_router == true) | .name'
}


# Phase 1: Path Discovery
phase1_path_discovery() {
    start_step "trace"
    
    local trace_result=""
    
    if [[ -n "$TRACE_FILE" ]]; then
        # Use provided trace file
        trace_result=$(cat "$TRACE_FILE")
        JSON_RESULTS[trace_source]="file"
        JSON_RESULTS[trace_file]="$TRACE_FILE"
    else
        # Execute live trace
        trace_result=$(tsimsh_exec "trace --source ${SOURCE_IP} --destination ${DEST_IP} --json" true)
        JSON_RESULTS[trace_source]="live"
    fi
    
    # Store trace result
    JSON_RESULTS[trace_result]="$trace_result"
    
    # Extract routers from trace
    local routers=$(extract_routers_from_trace "$trace_result")
    # Convert router list to JSON array using Python
    JSON_RESULTS[routers_in_path]=$(echo "$routers" | python3 -B -u -c "import sys, json; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))")
    
    end_step "$trace_result"
    
    echo "$routers"
}

# Phase 2: Simulation Environment Setup
phase2_setup_environment() {
    local routers="$1"
    
    start_step "environment_setup"
    
    # Get list of existing hosts
    local host_list=$(tsimsh_exec "host list --json" true)
    
    # Check which hosts already exist for each router
    local existing_source_hosts=""
    local existing_dest_hosts=""
    
    if [[ -n "$host_list" ]]; then
        # Extract existing hosts with matching IPs
        existing_source_hosts=$(echo "$host_list" | python3 -B -u -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    hosts = data.get('hosts', {})
    source_hosts = []
    for host_name, host_info in hosts.items():
        primary_ip = host_info.get('primary_ip', '')
        # Remove subnet mask for comparison
        if '/' in primary_ip:
            ip_only = primary_ip.split('/')[0]
            if ip_only == '${SOURCE_IP}':
                router = host_info.get('connected_to', '')
                source_hosts.append(f'{host_name}:{router}')
    print(' '.join(source_hosts))
except:
    pass
")
        
        existing_dest_hosts=$(echo "$host_list" | python3 -B -u -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    hosts = data.get('hosts', {})
    dest_hosts = []
    for host_name, host_info in hosts.items():
        primary_ip = host_info.get('primary_ip', '')
        # Remove subnet mask for comparison
        if '/' in primary_ip:
            ip_only = primary_ip.split('/')[0]
            if ip_only == '${DEST_IP}':
                router = host_info.get('connected_to', '')
                dest_hosts.append(f'{host_name}:{router}')
    print(' '.join(dest_hosts))
except:
    pass
")
    fi
    
    # Add source and destination hosts to EACH router
    local router_index=1
    local source_hosts_added=""
    local dest_hosts_added=""
    
    while IFS= read -r router; do
        [[ -z "$router" ]] && continue
        
        # Check if source host already exists for THIS router
        local source_exists_for_router=false
        for existing in $existing_source_hosts; do
            if [[ "$existing" == *":${router}" ]]; then
                source_exists_for_router=true
                break
            fi
        done
        
        # Add source host to this router if needed
        local src_host_name="source-${router_index}"
        if [[ "$source_exists_for_router" == "false" ]]; then
            if tsimsh_exec "host add --name ${src_host_name} --primary-ip ${SOURCE_IP}/24 --connect-to ${router}" false; then
                source_hosts_added+="${src_host_name} "
                SOURCE_HOST_ADDED=true
                CREATED_HOSTS+=("${src_host_name}")
            else
                # Clean up any hosts we've added so far
                for host in $source_hosts_added; do
                    tsimsh_exec "host remove --name ${host} --force" false || true
                done
                for host in $dest_hosts_added; do
                    tsimsh_exec "host remove --name ${host} --force" false || true
                done
                JSON_RESULTS[source_host_added]="false"
                end_step "failed"
                return 1
            fi
        fi
        
        # Check if destination host already exists for THIS router
        local dest_exists_for_router=false
        for existing in $existing_dest_hosts; do
            if [[ "$existing" == *":${router}" ]]; then
                dest_exists_for_router=true
                break
            fi
        done
        
        # Add destination host to this router if needed
        local dst_host_name="destination-${router_index}"
        if [[ "$dest_exists_for_router" == "false" ]]; then
            if tsimsh_exec "host add --name ${dst_host_name} --primary-ip ${DEST_IP}/24 --connect-to ${router}" false; then
                dest_hosts_added+="${dst_host_name} "
                DEST_HOST_ADDED=true
                CREATED_HOSTS+=("${dst_host_name}")
            else
                # Clean up any hosts we've added so far
                for host in $source_hosts_added; do
                    tsimsh_exec "host remove --name ${host} --force" false || true
                done
                for host in $dest_hosts_added; do
                    tsimsh_exec "host remove --name ${host} --force" false || true
                done
                JSON_RESULTS[destination_host_added]="false"
                end_step "failed"
                return 1
            fi
        fi
        
        ((router_index++))
    done <<< "$routers"
    
    # Store the list of hosts we added for cleanup later
    JSON_RESULTS[source_hosts_added]="$source_hosts_added"
    JSON_RESULTS[dest_hosts_added]="$dest_hosts_added"
    
    # Set status based on what we did
    if [[ -n "$source_hosts_added" ]]; then
        JSON_RESULTS[source_host_added]="true"
    else
        JSON_RESULTS[source_host_added]="false"
        if [[ -n "$existing_source_hosts" ]]; then
            JSON_RESULTS[source_host_existed]="true"
            JSON_RESULTS[existing_source_hosts]="$existing_source_hosts"
        fi
    fi
    
    if [[ -n "$dest_hosts_added" ]]; then
        JSON_RESULTS[destination_host_added]="true"
    else
        JSON_RESULTS[destination_host_added]="false"
        if [[ -n "$existing_dest_hosts" ]]; then
            JSON_RESULTS[destination_host_existed]="true"
            JSON_RESULTS[existing_dest_hosts]="$existing_dest_hosts"
        fi
    fi
    
    # Check if service is already running
    local service_list=$(tsimsh_exec "service list --json" true)
    local service_exists=false
    
    if [[ -n "$service_list" ]]; then
        # Check if this specific service is already running
        service_exists=$(echo "$service_list" | python3 -B -u -c "
import sys, json
try:
    services = json.loads(sys.stdin.read())
    for service in services:
        if (service.get('bind_address') == '${DEST_IP}' and 
            str(service.get('port')) == '${DEST_PORT}' and 
            service.get('protocol', '').lower() == '${PROTOCOL}'.lower() and
            service.get('status') == 'running'):
            print('true')
            break
except:
    pass
")
    fi
    
    # Start destination service only if it doesn't exist
    if [[ "$service_exists" != "true" ]]; then
        if tsimsh_exec "service start --ip ${DEST_IP} --port ${DEST_PORT} --protocol ${PROTOCOL}" false; then
            SERVICE_STARTED=true
            JSON_RESULTS[service_started]="true"
        else
            JSON_RESULTS[service_started]="false"
            end_step "failed"
            return 1
        fi
    else
        SERVICE_STARTED=false
        JSON_RESULTS[service_started]="false"
        JSON_RESULTS[service_existed]="true"
    fi
    
    end_step "completed"
    return 0
}

# Phase 3: Initial Reachability Tests
phase3_reachability_tests() {
    start_step "reachability_tests"
    
    local overall_result="success"
    
    # Run all three tests in parallel
    local ping_file="${TEMP_DIR}/ping_result.json"
    local mtr_file="${TEMP_DIR}/traceroute_result.json"
    local service_file="${TEMP_DIR}/service_result.json"
    
    log_timing "TESTS_PARALLEL_START" "ping, traceroute, service"
    
    # Test 1: ICMP Ping (background)
    {
        log_timing "PING_START"
        start_step "ping"
        local ping_output
        ping_output=$(tsimsh_exec "ping --source ${SOURCE_IP} --destination ${DEST_IP} --timeout 1 --count 2 --json" true)
        local ping_rc=$?
        echo "$ping_output" > "$ping_file"
        echo $ping_rc > "${ping_file}.rc"
        log_timing "PING_END" "rc=$ping_rc"
    } &
    local ping_pid=$!
    
    # Test 2: Traceroute (background)
    {
        log_timing "TRACEROUTE_START"
        start_step "traceroute"
        local traceroute_output
        traceroute_output=$(tsimsh_exec "traceroute --source ${SOURCE_IP} --destination ${DEST_IP} --json" true)
        local traceroute_rc=$?
        echo "$traceroute_output" > "$mtr_file"
        echo $traceroute_rc > "${mtr_file}.rc"
        log_timing "TRACEROUTE_END" "rc=$traceroute_rc"
    } &
    local mtr_pid=$!
    
    # Test 3: Service Test (background)
    {
        log_timing "SERVICE_TEST_START"
        start_step "service_test"
        local service_output
        service_output=$(tsimsh_exec "service test --source ${SOURCE_IP} --destination ${DEST_IP}:${DEST_PORT} --protocol ${PROTOCOL} --timeout 1 --json" true)
        local service_rc=$?
        echo "$service_output" > "$service_file"
        echo $service_rc > "${service_file}.rc"
        log_timing "SERVICE_TEST_END" "rc=$service_rc"
    } &
    local service_pid=$!
    
    # Wait for all tests to complete
    wait $ping_pid
    wait $mtr_pid
    wait $service_pid
    log_timing "TESTS_PARALLEL_END" "all tests complete"
    
    # Collect results
    local ping_result=$(cat "$ping_file" 2>/dev/null || echo "{}")
    local ping_return=$(cat "${ping_file}.rc" 2>/dev/null || echo "1")
    JSON_RESULTS[ping_result]="$ping_result"
    JSON_RESULTS[ping_return_code]="$ping_return"
    end_step "$ping_result"
    
    local mtr_result=$(cat "$mtr_file" 2>/dev/null || echo "{}")
    local mtr_return=$(cat "${mtr_file}.rc" 2>/dev/null || echo "1")
    JSON_RESULTS[mtr_result]="$mtr_result"
    JSON_RESULTS[mtr_return_code]="$mtr_return"
    end_step "$mtr_result"
    
    local service_result=$(cat "$service_file" 2>/dev/null || echo "{}")
    local service_return=$(cat "${service_file}.rc" 2>/dev/null || echo "1")
    JSON_RESULTS[service_result]="$service_result"
    JSON_RESULTS[service_return_code]="$service_return"
    end_step "$service_result"
    
    # Analyze service test results to determine reachability per router
    # Get all routers from the trace path
    local all_routers="${JSON_RESULTS[routers_in_path]:-[]}"
    
    if [[ -z "$service_result" || "$service_result" == "{}" ]]; then
        echo "Error: Service test results are missing. Cannot determine router allow/block status." >&2
        exit 1
    fi
    
    local router_results=$(echo "$service_result" | python3 -B -u -c "
import sys, json

try:
    data = json.loads(sys.stdin.read())
    all_routers = json.loads('$all_routers')
    
    if 'tests' not in data or not data['tests']:
        print('ERROR: No service tests found in results')
        sys.exit(1)
    
    # Build results from service tests
    results = {}
    
    # Process each test result
    for test in data['tests']:
        if 'via_router' in test:
            router = test['via_router']
            status = test.get('status', '')
            
            if status == 'OK':
                results[router] = 'ALLOWED'
            elif status in ['FAIL', 'TIMEOUT', 'ERROR']:
                results[router] = 'BLOCKED'
            else:
                print(f'ERROR: Unknown status {status} for router {router}')
                sys.exit(1)
    
    # Verify we have results for all routers
    missing_routers = set(all_routers) - set(results.keys())
    if missing_routers:
        print(f'ERROR: Missing service test results for routers: {list(missing_routers)}')
        sys.exit(1)
    
    print(json.dumps(results))
    
except Exception as e:
    print(f'ERROR: Failed to parse service test results: {e}')
    sys.exit(1)
")
    
    # Check if Python script reported an error
    if [[ "$router_results" == ERROR:* ]]; then
        echo "$router_results" >&2
        exit 1
    fi
    
    JSON_RESULTS[router_service_results]="$router_results"
    
    # Overall status based on service test
    if [[ $service_return -eq 0 ]]; then
        overall_result="service_reachable"
    else
        overall_result="service_unreachable"
    fi
    
    end_step "$overall_result"
    
    return $service_return
}

# Phase 4: Packet Count Analysis
phase4_packet_analysis() {
    local routers="$1"
    local service_failed="$2"
    
    start_step "packet_count_analysis"
    
    # Prepare router array for parallel processing
    local router_array=()
    while IFS= read -r router; do
        [[ -z "$router" ]] && continue
        router_array+=("$router")
    done <<< "$routers"
    
    # Step 1: Get "before" snapshots for ALL routers in parallel
    local before_pids=()
    for router in "${router_array[@]}"; do
        {
            local before_file="${TEMP_DIR}/${router}_before.json"
            tsimsh_exec "network status --limit ${router} iptables --json" true > "$before_file"
        } &
        before_pids+=($!)
    done
    
    # Wait for all "before" snapshots to complete
    for pid in "${before_pids[@]}"; do
        wait $pid
    done
    
    # Step 2: Execute test traffic once (this affects all routers)
    tsimsh_exec "service test --source ${SOURCE_IP} --destination ${DEST_IP}:${DEST_PORT} --protocol ${PROTOCOL} --timeout 1 --json" true >/dev/null
    
    # Step 3: Get "after" snapshots for ALL routers in parallel
    local after_pids=()
    for router in "${router_array[@]}"; do
        {
            local after_file="${TEMP_DIR}/${router}_after.json"
            tsimsh_exec "network status --limit ${router} iptables --json" true > "$after_file"
        } &
        after_pids+=($!)
    done
    
    # Wait for all "after" snapshots to complete
    for pid in "${after_pids[@]}"; do
        wait $pid
    done
    
    # Step 4: Analyze packet counts for all routers in parallel
    local analysis_pids=()
    local analysis_results_dir="${TEMP_DIR}/analysis_results"
    mkdir -p "$analysis_results_dir"
    
    for router in "${router_array[@]}"; do
        local result_file="${analysis_results_dir}/${router}.json"
        {
            # Determine analysis mode based on the service test result for THIS specific router
            local analysis_mode="blocking"  # default to blocking
            if [[ -n "${JSON_RESULTS[router_service_results]}" ]]; then
                # Extract the status for this specific router from router_service_results
                local router_status=$(echo "${JSON_RESULTS[router_service_results]}" | python3 -B -u -c "
import sys, json
try:
    data = json.loads(sys.stdin.read())
    print(data.get('$router', 'FAIL'))
except:
    print('FAIL')
")
                if [[ "$router_status" == "ALLOWED" ]]; then
                    analysis_mode="allowing"
                fi
            fi
            
            start_step "analyze_packet_counts.py $router -m $analysis_mode"
            
            local before_file="${TEMP_DIR}/${router}_before.json"
            local after_file="${TEMP_DIR}/${router}_after.json"
            
            # Run packet count analysis with appropriate mode
            echo "$(get_elapsed_time) ${SCRIPT_DIR}/analyze_packet_counts.py $router $before_file $after_file -m $analysis_mode" >&2
            "${SCRIPT_DIR}/analyze_packet_counts.py" "$router" "$before_file" "$after_file" -m "$analysis_mode" > "$result_file" 2>/dev/null || echo "{}" > "$result_file"
            
            end_step "completed"
        } &
        analysis_pids+=($!)
    done
    
    # Wait for all analyses to complete
    for pid in "${analysis_pids[@]}"; do
        wait $pid
    done
    
    # Step 5: Gather results from analyzer processes
    local packet_analysis_results=()
    for router in "${router_array[@]}"; do
        local result_file="${analysis_results_dir}/${router}.json"
        if [[ -f "$result_file" ]]; then
            local result=$(cat "$result_file")
            if [[ -n "$result" && "$result" != "{}" ]]; then
                packet_analysis_results+=("$result")
            fi
        fi
    done
    
    # Combine all packet analysis results
    if [[ ${#packet_analysis_results[@]} -gt 0 ]]; then
        # Use Python to combine JSON results
        JSON_RESULTS[packet_count_analysis]=$(printf '%s\n' "${packet_analysis_results[@]}" | python3 -B -u -c "
import sys, json
results = []
for line in sys.stdin:
    line = line.strip()
    if line:
        try:
            results.append(json.loads(line))
        except:
            pass
print(json.dumps(results))
")
    else
        JSON_RESULTS[packet_count_analysis]="[]"
    fi
    
    end_step "completed"
}

# Phase 5: Result Compilation
phase5_compile_results() {
    start_step "format_reachability_output.py"
    
    # Build execution trace as JSON array
    local execution_trace="["
    local first=true
    for ((i=1; i<=STEP_COUNTER; i++)); do
        local name_key="${i}_name"
        local duration_key="${i}_duration"
        local result_key="${i}_result"
        
        local step_name="${STEP_TIMERS[$name_key]:-}"
        local duration="${STEP_TIMERS[$duration_key]:-0}"
        local result="${STEP_TIMERS[$result_key]:-}"
        
        if [[ -n "$step_name" ]]; then
            if [[ "$first" != "true" ]]; then
                execution_trace+=","
            fi
            first=false
            # Use Python to properly escape JSON strings
            local result_json=$(echo "$result" | python3 -B -u -c "import sys, json; print(json.dumps(sys.stdin.read().strip()))")
            execution_trace+="{\"step\": \"$step_name\", \"duration_seconds\": $duration, \"result\": $result_json}"
        fi
    done
    execution_trace+="]"
    
    # Export all data as environment variables for Python script
    export SOURCE_IP
    export SOURCE_PORT
    export DEST_IP
    export DEST_PORT
    export PROTOCOL
    export VERSION
    export TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    # Export test results
    export PING_RESULT="${JSON_RESULTS[ping_result]:-}"
    export PING_RETURN_CODE="${JSON_RESULTS[ping_return_code]:-}"
    export TRACEROUTE_RESULT="${JSON_RESULTS[mtr_result]:-}"
    export TRACEROUTE_RETURN_CODE="${JSON_RESULTS[mtr_return_code]:-}"
    export SERVICE_RESULT="${JSON_RESULTS[service_result]:-}"
    export SERVICE_RETURN_CODE="${JSON_RESULTS[service_return_code]:-}"
    
    # Export other data
    export TRACE_RESULT="${JSON_RESULTS[trace_result]:-}"
    export ROUTERS_IN_PATH="${JSON_RESULTS[routers_in_path]:-}"
    export PACKET_COUNT_ANALYSIS="${JSON_RESULTS[packet_count_analysis]:-}"
    export ROUTER_SERVICE_RESULTS="${JSON_RESULTS[router_service_results]:-}"
    export EXECUTION_TRACE="$execution_trace"
    
    # Export setup status
    export SOURCE_HOST_ADDED="${JSON_RESULTS[source_host_added]:-false}"
    export DEST_HOST_ADDED="${JSON_RESULTS[destination_host_added]:-false}"
    export SERVICE_STARTED="${JSON_RESULTS[service_started]:-false}"
    
    end_step "completed"
    
    # Use Python script to format output
    # Use env to ensure all exported variables are passed to the Python script
    env "${SCRIPT_DIR}/format_reachability_output.py"
}

# Main execution
main() {
    log_timing "SCRIPT_START" "$SOURCE_IP -> $DEST_IP:$DEST_PORT"
    
    # Parse and validate arguments
    log_timing "PARSE_ARGS_START"
    parse_args "$@"
    validate_params
    log_timing "PARSE_ARGS_END"
    
    # Execute phases
    log_timing "PHASE1_START" "Path discovery"
    local routers
    routers=$(phase1_path_discovery)
    log_timing "PHASE1_END" "Found $(echo "$routers" | wc -l) routers"
    
    if [[ -z "$routers" ]]; then
        echo "{\"error\": \"No routers found in trace path\"}" | jq .
        exit 1
    fi
    
    log_timing "PHASE2_START" "Environment setup"
    if ! phase2_setup_environment "$routers"; then
        log_timing "PHASE2_FAILED"
        echo "{\"error\": \"Failed to setup simulation environment\"}" | jq .
        exit 1
    fi
    log_timing "PHASE2_END"
    
    log_timing "PHASE3_START" "Reachability tests (ping/traceroute/service)"
    local service_test_failed=false
    if ! phase3_reachability_tests; then
        service_test_failed=true
    fi
    log_timing "PHASE3_END"
    
    # Always run packet analysis with appropriate mode
    log_timing "PHASE4_START" "Packet count analysis"
    phase4_packet_analysis "$routers" "$service_test_failed"
    log_timing "PHASE4_END"
    
    # Compile and output results
    log_timing "PHASE5_START" "Format output"
    phase5_compile_results
    log_timing "PHASE5_END"
    
    log_timing "SCRIPT_END" "Complete"
    
    # Exit with appropriate code based on service test result
    if [[ "${JSON_RESULTS[service_return_code]}" == "0" ]]; then
        exit 0
    else
        exit 1
    fi
}

# Run main function
main "$@"
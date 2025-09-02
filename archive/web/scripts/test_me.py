#!/usr/bin/env -S python3 -B -u
"""
Simple test script to debug environment and permissions from web interface
"""
import subprocess
import json
import sys
import os

def main():
    """Run env and id commands and output results as JSON"""
    results = {}
    
    # Run env command before sourcing venv
    try:
        env_result = subprocess.run(['env'], capture_output=True, text=True)
        results['env_before_venv'] = {
            'stdout': env_result.stdout,
            'stderr': env_result.stderr,
            'returncode': env_result.returncode
        }
    except Exception as e:
        results['env_before_venv'] = {'error': str(e)}
    
    # Run id command
    try:
        id_result = subprocess.run(['id'], capture_output=True, text=True)
        results['id'] = {
            'stdout': id_result.stdout,
            'stderr': id_result.stderr,
            'returncode': id_result.returncode
        }
    except Exception as e:
        results['id'] = {'error': str(e)}
    
    # Source venv and run env command again
    venv_path = os.environ.get('VIRTUAL_ENV', '/home/sparavec/tsim-venv')
    try:
        # Use bash to source the venv activate script and then run env
        bash_cmd = f'source {venv_path}/bin/activate && env'
        env_after_result = subprocess.run(['bash', '-c', bash_cmd], capture_output=True, text=True)
        results['env_after_venv'] = {
            'stdout': env_after_result.stdout,
            'stderr': env_after_result.stderr,
            'returncode': env_after_result.returncode
        }
    except Exception as e:
        results['env_after_venv'] = {'error': str(e)}
    
    # Run tsimsh host list command
    try:
        # Use bash to source the venv activate script and then run tsimsh
        tsimsh_cmd = f'source {venv_path}/bin/activate && echo "host list -j" | tsimsh -q'
        tsimsh_result = subprocess.run(['bash', '-c', tsimsh_cmd], capture_output=True, text=True)
        results['tsimsh_host_list'] = {
            'stdout': tsimsh_result.stdout,
            'stderr': tsimsh_result.stderr,
            'returncode': tsimsh_result.returncode
        }
    except Exception as e:
        results['tsimsh_host_list'] = {'error': str(e)}
    
    # Run tsimsh host add command
    try:
        # Use bash to source the venv activate script and then run tsimsh
        host_add_cmd = f'source {venv_path}/bin/activate && echo "host add --name source-1 --primary-ip 10.129.130.21/24 --connect-to befw-eldok2-01.lvnbb.de" | tsimsh -q'
        host_add_result = subprocess.run(['bash', '-c', host_add_cmd], capture_output=True, text=True)
        results['tsimsh_host_add'] = {
            'stdout': host_add_result.stdout,
            'stderr': host_add_result.stderr,
            'returncode': host_add_result.returncode
        }
    except Exception as e:
        results['tsimsh_host_add'] = {'error': str(e)}
    
    # List traceroute files in /tmp
    try:
        # Use bash -c to properly execute the ls command with wildcard
        ls_cmd = 'ls -al /tmp/traceroute*'
        ls_result = subprocess.run(['bash', '-c', ls_cmd], capture_output=True, text=True)
        results['ls_traceroute_files'] = {
            'stdout': ls_result.stdout,
            'stderr': ls_result.stderr,
            'returncode': ls_result.returncode
        }
    except Exception as e:
        results['ls_traceroute_files'] = {'error': str(e)}
    
    # Check actual tmp directory and mount info
    try:
        tmp_check_cmd = 'df -h /tmp && echo "---" && stat -f /tmp && echo "---" && findmnt /tmp'
        tmp_check_result = subprocess.run(['bash', '-c', tmp_check_cmd], capture_output=True, text=True)
        results['tmp_directory_info'] = {
            'stdout': tmp_check_result.stdout,
            'stderr': tmp_check_result.stderr,
            'returncode': tmp_check_result.returncode
        }
    except Exception as e:
        results['tmp_directory_info'] = {'error': str(e)}
    
    # Check /var/opt/traceroute-simulator directory
    try:
        var_opt_cmd = '''
        echo "=== Directory listing ==="
        ls -la /var/opt/traceroute-simulator/
        echo -e "\n=== File contents ==="
        for file in /var/opt/traceroute-simulator/*; do
            if [ -f "$file" ]; then
                echo -e "\n--- $file ---"
                head -20 "$file"
            fi
        done
        '''
        var_opt_result = subprocess.run(['bash', '-c', var_opt_cmd], capture_output=True, text=True)
        results['var_opt_traceroute'] = {
            'stdout': var_opt_result.stdout,
            'stderr': var_opt_result.stderr,
            'returncode': var_opt_result.returncode
        }
    except Exception as e:
        results['var_opt_traceroute'] = {'error': str(e)}
    
    # Output as JSON
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
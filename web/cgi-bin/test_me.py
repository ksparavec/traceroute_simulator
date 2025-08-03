#!/usr/bin/env -S python3 -B -u
"""
CGI script to run test_me.py and display environment/permission info
"""
import cgi
import cgitb
import os
import sys
import json
import subprocess
from http import cookies

sys.path.append(os.path.join(os.path.dirname(__file__), 'lib'))

from session import SessionManager
from config import Config
from logger import AuditLogger

# Enable error logging but not display
cgitb.enable(display=0, logdir="/var/www/traceroute-web/logs")

def get_session_id():
    """Extract session ID from cookie"""
    cookie_str = os.environ.get('HTTP_COOKIE', '')
    cookie = cookies.SimpleCookie(cookie_str)
    if 'session_id' in cookie:
        return cookie['session_id'].value
    return None

def main():
    try:
        # Initialize components
        config = Config()
        session_mgr = SessionManager()
        logger = AuditLogger()
        
        # Check session
        session_id = get_session_id()
        session = session_mgr.get_session(session_id)
        
        if not session:
            print("Status: 302 Found")
            print("Location: /login.html")
            print()
            return
        
        # Log the test execution
        logger.log_info(f"TEST ME executed by {session['username']} (session: {session_id})")
        
        # Build environment for test_me.py
        simulator_path = config.config.get('traceroute_simulator_path', '/opt/traceroute_simulator')
        venv_path = config.config.get('venv_path', '/home/sparavec/tsim-venv')
        facts_path = config.config.get('traceroute_simulator_facts', '/var/local/tsim_facts')
        raw_facts_path = config.config.get('traceroute_simulator_raw_facts', '/var/local/tsim_raw_facts')
        conf_path = config.config.get('traceroute_simulator_conf', '/var/www/traceroute-web/conf/traceroute_simulator.yaml')
        
        env = {
            # Basic environment
            'PATH': f"{venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            'VIRTUAL_ENV': venv_path,
            'PYTHONPATH': simulator_path,
            'HOME': '/tmp',
            'USER': 'www-data',
            'SHELL': '/bin/bash',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
            
            # Traceroute simulator specific
            'TRACEROUTE_SIMULATOR_RAW_FACTS': raw_facts_path,
            'TRACEROUTE_SIMULATOR_FACTS': facts_path,
            'TRACEROUTE_SIMULATOR_CONF': conf_path,
        }
        
        # Execute test_me.py using the same method as network_reachability_test.sh
        test_script = os.path.join(simulator_path, 'test_me.py')
        venv_activate = os.path.join(venv_path, 'bin', 'activate')
        
        # Build command to source venv and run script
        cmd = ['bash', '-c', f'source {venv_activate} && {venv_path}/bin/python -B -u {test_script}']
        
        try:
            result = subprocess.run(
                cmd,
                env=env,
                cwd=simulator_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse the JSON output
            if result.returncode == 0:
                try:
                    output_data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    output_data = {
                        'error': 'Failed to parse JSON output',
                        'stdout': result.stdout,
                        'stderr': result.stderr
                    }
            else:
                output_data = {
                    'error': 'Script execution failed',
                    'returncode': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr
                }
                
        except subprocess.TimeoutExpired:
            output_data = {'error': 'Script execution timed out'}
        except Exception as e:
            output_data = {'error': f'Failed to execute script: {str(e)}'}
        
        # Generate HTML output
        print("Content-Type: text/html\n")
        print("""<!DOCTYPE html>
<html>
<head>
    <title>Test Results - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
    <style>
        .test-results {
            background: #f0f0f0;
            padding: 20px;
            margin: 20px;
            border-radius: 5px;
        }
        .test-section {
            background: white;
            padding: 15px;
            margin: 10px 0;
            border-radius: 3px;
            border: 1px solid #ddd;
        }
        .test-section h3 {
            margin-top: 0;
            color: #333;
        }
        pre {
            background: #f8f8f8;
            padding: 10px;
            overflow-x: auto;
            border: 1px solid #e0e0e0;
            border-radius: 3px;
        }
        .error {
            color: #d00;
            font-weight: bold;
        }
        .back-link {
            display: inline-block;
            margin: 20px;
            padding: 10px 20px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 3px;
        }
        .back-link:hover {
            background: #0056b3;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Test Results</h1>
        <div class="test-results">
""")
        
        if 'error' in output_data and not ('env_before_venv' in output_data or 'id' in output_data):
            # Top-level error
            print(f'<div class="test-section error">')
            print(f'<h3>Error</h3>')
            print(f'<pre>{output_data["error"]}</pre>')
            if 'stdout' in output_data:
                print(f'<h4>Standard Output:</h4>')
                print(f'<pre>{output_data["stdout"]}</pre>')
            if 'stderr' in output_data:
                print(f'<h4>Standard Error:</h4>')
                print(f'<pre>{output_data["stderr"]}</pre>')
            print('</div>')
        else:
            # Function to process and display environment variables
            def display_env_section(title, env_data):
                print(f'<div class="test-section">')
                print(f'<h3>{title}</h3>')
                if 'error' in env_data:
                    print(f'<p class="error">Error: {env_data["error"]}</p>')
                else:
                    env_lines = env_data['stdout'].strip().split('\n')
                    # Sort and display key environment variables
                    env_dict = {}
                    for line in env_lines:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_dict[key] = value
                    
                    # Highlight important variables
                    important_vars = [
                        'PATH', 'PYTHONPATH', 'USER', 'HOME',
                        'TRACEROUTE_SIMULATOR_FACTS',
                        'TRACEROUTE_SIMULATOR_RAW_FACTS',
                        'TRACEROUTE_SIMULATOR_CONF',
                        'VIRTUAL_ENV'
                    ]
                    
                    print('<h4>Key Variables:</h4>')
                    print('<pre>')
                    for var in important_vars:
                        if var in env_dict:
                            print(f'{var}={env_dict[var]}')
                    print('</pre>')
                    
                    print('<h4>All Variables:</h4>')
                    print(f'<pre>{env_data["stdout"]}</pre>')
                print('</div>')
            
            # Environment before venv
            if 'env_before_venv' in output_data:
                display_env_section('Environment Variables (Before venv)', output_data['env_before_venv'])
            
            # Environment after venv
            if 'env_after_venv' in output_data:
                display_env_section('Environment Variables (After venv)', output_data['env_after_venv'])
            
            # User/Group info section
            if 'id' in output_data:
                print('<div class="test-section">')
                print('<h3>User and Group Information</h3>')
                if 'error' in output_data['id']:
                    print(f'<p class="error">Error: {output_data["id"]["error"]}</p>')
                else:
                    print(f'<pre>{output_data["id"]["stdout"]}</pre>')
                print('</div>')
            
            # Tsimsh host list section
            if 'tsimsh_host_list' in output_data:
                print('<div class="test-section">')
                print('<h3>Tsimsh Host List</h3>')
                tsimsh_data = output_data['tsimsh_host_list']
                if 'error' in tsimsh_data:
                    print(f'<p class="error">Error: {tsimsh_data["error"]}</p>')
                else:
                    print(f'<h4>Return Code: {tsimsh_data["returncode"]}</h4>')
                    if tsimsh_data['stdout']:
                        print('<h4>Standard Output:</h4>')
                        print(f'<pre>{tsimsh_data["stdout"]}</pre>')
                    if tsimsh_data['stderr']:
                        print('<h4>Standard Error:</h4>')
                        print(f'<pre class="error">{tsimsh_data["stderr"]}</pre>')
                print('</div>')
            
            # Tsimsh host add section
            if 'tsimsh_host_add' in output_data:
                print('<div class="test-section">')
                print('<h3>Tsimsh Host Add</h3>')
                print('<p><strong>Command:</strong> <code>host add --name source-1 --primary-ip 10.129.130.21/24 --connect-to befw-eldok2-01.lvnbb.de</code></p>')
                tsimsh_data = output_data['tsimsh_host_add']
                if 'error' in tsimsh_data:
                    print(f'<p class="error">Error: {tsimsh_data["error"]}</p>')
                else:
                    print(f'<h4>Return Code: {tsimsh_data["returncode"]}</h4>')
                    if tsimsh_data['stdout']:
                        print('<h4>Standard Output:</h4>')
                        print(f'<pre>{tsimsh_data["stdout"]}</pre>')
                    if tsimsh_data['stderr']:
                        print('<h4>Standard Error:</h4>')
                        print(f'<pre class="error">{tsimsh_data["stderr"]}</pre>')
                print('</div>')
            
            # List traceroute files section
            if 'ls_traceroute_files' in output_data:
                print('<div class="test-section">')
                print('<h3>Traceroute Registry Files</h3>')
                print('<p><strong>Command:</strong> <code>ls -al /tmp/traceroute*</code></p>')
                ls_data = output_data['ls_traceroute_files']
                if 'error' in ls_data:
                    print(f'<p class="error">Error: {ls_data["error"]}</p>')
                else:
                    print(f'<h4>Return Code: {ls_data["returncode"]}</h4>')
                    if ls_data['stdout']:
                        print(f'<h4>Files Found: (Length: {len(ls_data["stdout"])} chars)</h4>')
                        import html
                        print(f'<pre>{html.escape(ls_data["stdout"])}</pre>')
                    if ls_data['stderr']:
                        print('<h4>Error Output:</h4>')
                        print(f'<pre class="error">{ls_data["stderr"]}</pre>')
                print('</div>')
            
            # Tmp directory info section
            if 'tmp_directory_info' in output_data:
                print('<div class="test-section">')
                print('<h3>Tmp Directory Information</h3>')
                print('<p><strong>Commands:</strong> <code>df -h /tmp</code>, <code>stat -f /tmp</code>, <code>findmnt /tmp</code></p>')
                tmp_data = output_data['tmp_directory_info']
                if 'error' in tmp_data:
                    print(f'<p class="error">Error: {tmp_data["error"]}</p>')
                else:
                    if tmp_data['stdout']:
                        print('<h4>Output:</h4>')
                        print(f'<pre>{html.escape(tmp_data["stdout"])}</pre>')
                    if tmp_data['stderr']:
                        print('<h4>Error Output:</h4>')
                        print(f'<pre class="error">{tmp_data["stderr"]}</pre>')
                print('</div>')
            
            # /var/opt/traceroute-simulator section
            if 'var_opt_traceroute' in output_data:
                print('<div class="test-section">')
                print('<h3>/var/opt/traceroute-simulator Directory</h3>')
                print('<p><strong>Commands:</strong> <code>ls -la /var/opt/traceroute-simulator/</code> and file contents</p>')
                var_opt_data = output_data['var_opt_traceroute']
                if 'error' in var_opt_data:
                    print(f'<p class="error">Error: {var_opt_data["error"]}</p>')
                else:
                    if var_opt_data['stdout']:
                        print('<h4>Output:</h4>')
                        print(f'<pre>{html.escape(var_opt_data["stdout"])}</pre>')
                    if var_opt_data['stderr']:
                        print('<h4>Error Output:</h4>')
                        print(f'<pre class="error">{var_opt_data["stderr"]}</pre>')
                print('</div>')
        
        print("""
        </div>
        <a href="/form.html" class="back-link">Back to Form</a>
    </div>
</body>
</html>""")
        
    except Exception as e:
        # Log error
        if 'logger' in locals():
            logger.log_error(
                error_type=type(e).__name__,
                error_msg=str(e),
                session_id=session_id if 'session_id' in locals() else None,
                traceback=True
            )
        
        # Show error page
        print("Content-Type: text/html\n")
        print("""<!DOCTYPE html>
<html>
<head>
    <title>Error - Network Reachability Test</title>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <div class="error-container">
        <h1>Error</h1>
        <p>An error occurred while running the test.</p>
        <a href="/form.html">Back to form</a>
    </div>
</body>
</html>""")

if __name__ == "__main__":
    main()
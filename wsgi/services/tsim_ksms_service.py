#!/usr/bin/env -S python3 -B -u
"""
TSIM KSMS Service
Integration service for high-performance KSMS (Kernel-Space Multi-Service) tester
"""

import os
import sys
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from .tsim_dscp_registry import TsimDscpRegistry


def tsimsh_exec(command: str, capture_output: bool = False, verbose: int = 0, env: dict = None) -> Optional[str]:
    """Execute tsimsh command (copied exactly from MultiServiceTester pattern)"""
    # Always use tsimsh from PATH (properly installed version)
    tsimsh_path = "tsimsh"
    
    cmd = [tsimsh_path, "-q"]
    
    try:
        result = subprocess.run(
            cmd,
            input=command,
            capture_output=True,
            text=True,
            timeout=60,
            env=env
        )
        
        # Debug output for verbose mode
        if verbose > 0:
            print(f"[DEBUG] tsimsh command: {command}", file=sys.stderr)
            if verbose > 1:
                print(f"[DEBUG] tsimsh stdout: {result.stdout[:500]}", file=sys.stderr)
                print(f"[DEBUG] tsimsh stderr: {result.stderr[:200]}", file=sys.stderr)
            print(f"[DEBUG] tsimsh return code: {result.returncode}", file=sys.stderr)
        
        if result.returncode != 0:
            if verbose > 0:
                print(f"[ERROR] tsimsh command failed: {result.stderr}", file=sys.stderr)
            return None
            
        if capture_output:
            return result.stdout
        return None if result.returncode == 0 else result.stderr
    except Exception as e:
        print(f"Error executing tsimsh command: {e}", file=sys.stderr)
        return None


class TsimKsmsService:
    """KSMS integration service for quick analysis mode"""
    
    def __init__(self, config_service):
        """Initialize KSMS service
        
        Args:
            config_service: TsimConfigService instance
        """
        self.config = config_service
        self.logger = logging.getLogger('tsim.ksms')
        self.dscp_registry = TsimDscpRegistry(config_service)
        
        # KSMS configuration
        self.enabled = config_service.get('ksms_enabled', True)
        self.timeout = config_service.get('ksms_timeout', 300)
        self.tsimsh_path = config_service.get('tsimsh_path', 'tsimsh')
        
        self.logger.info(f"KSMS Service initialized: enabled={self.enabled}, "
                        f"tsimsh_path={self.tsimsh_path}")
    
    
    def execute_quick_analysis(self, params: Dict[str, Any], progress_callback=None) -> Dict[str, Any]:
        """Execute KSMS quick analysis mode
        
        Args:
            params: Job parameters
            
        Returns:
            Analysis results in service-based format for PDF compatibility
        """
        if not self.enabled:
            raise RuntimeError("KSMS is disabled in configuration")
        
        run_id = params['run_id']
        source_ip = params['source_ip']
        dest_ip = params['dest_ip']
        
        services = params['services']  # List of parsed services
        
        self.logger.info(f"Starting KSMS quick analysis: {run_id}, {len(services)} services")
        
        # Helper function for progress logging
        def log_progress(phase: str, message: str):
            if progress_callback:
                try:
                    progress_callback(phase, message)
                    self.logger.debug(f"Progress logged: {phase}")
                except Exception as e:
                    self.logger.error(f"Failed to log progress {phase}: {e}")
        
        try:
            # Step 1: Update progress - Start
            log_progress('PHASE2_ksms_start', f'Starting KSMS quick analysis for {len(services)} services')
            
            # Step 2: Allocate DSCP
            job_dscp = self.dscp_registry.allocate_dscp(run_id)
            if job_dscp is None:
                raise RuntimeError("No DSCP values available - too many concurrent jobs")
            
            self.logger.info(f"Allocated DSCP {job_dscp} for job {run_id}")
            
            try:
                # Step 3: Setup source hosts from trace
                log_progress('PHASE2_host_setup', 'Creating source hosts from trace')
                
                routers = self._setup_source_hosts(params, run_id, log_progress)
                
                # Step 4: Execute KSMS bulk scan
                log_progress('PHASE3_ksms_scan', f'Executing KSMS bulk scan with DSCP {job_dscp}')
                
                ksms_results = self._execute_ksms_scan(source_ip, dest_ip, services, job_dscp, run_id)
                
                # Step 5: Cleanup source hosts
                log_progress('PHASE3_cleanup', 'Removing created source hosts')
                
                self._cleanup_source_hosts(routers, run_id)
                
                # Step 6: Convert to service format for PDF compatibility
                log_progress('PHASE4_format', 'Converting KSMS results for PDF generation')
                
                service_format_results = self._convert_to_service_format(ksms_results, params)
                
                # Step 7: Generate PDF
                log_progress('PHASE4_pdf', 'Generating KSMS summary PDF')
                
                pdf_result = self._generate_summary_pdf(service_format_results, params, ksms_results)
                
                # Complete
                log_progress('PHASE4_complete', 'KSMS scan and analysis completed')
                
                # Note: PDF URL is handled by hybrid executor
                
                final_result = {
                    'run_id': run_id,
                    'analysis_mode': 'quick',
                    'services_analyzed': len(services),
                    'ksms_results': ksms_results,
                    'service_results': service_format_results,
                    'pdf_result': pdf_result,
                    'dscp_used': job_dscp
                }
                
                self.logger.info(f"KSMS quick analysis completed: {run_id}")
                return final_result
                
            finally:
                # Always release DSCP
                self.dscp_registry.release_dscp(run_id)
                self.logger.info(f"Released DSCP {job_dscp} for job {run_id}")
        
        except Exception as e:
            log_progress('ERROR', f'KSMS analysis failed: {str(e)}')
            self.logger.error(f"KSMS quick analysis failed for {run_id}: {e}")
            raise
    
    def _execute_ksms_scan(self, source_ip: str, dest_ip: str, services: List[Dict], 
                          job_dscp: int, run_id: str) -> Dict[str, Any]:
        """Execute ksms_tester subprocess
        
        Returns:
            Raw KSMS results in router-based format
        """
        # Build port specification
        port_specs = []
        for svc in services:
            port_specs.append(f"{svc['port']}/{svc['protocol']}")
        ports_arg = ",".join(port_specs)
        
        # Build KSMS command exactly like service test pattern
        ksms_command = f"ksms_tester -s {source_ip} -d {dest_ip} -P {ports_arg} -j"
        
        # Set environment with DSCP
        env = os.environ.copy()
        env['KSMS_JOB_DSCP'] = str(job_dscp)
        
        self.logger.debug(f"Executing KSMS command: {ksms_command}")
        self.logger.debug(f"KSMS environment: KSMS_JOB_DSCP={job_dscp}")
        
        # Use the same tsimsh_exec pattern as MultiServiceTester
        ksms_output = tsimsh_exec(ksms_command, capture_output=True, verbose=1, env=env)
        
        # Debug: Log what we got back
        self.logger.info(f"KSMS command returned: {repr(ksms_output)}")
        self.logger.info(f"KSMS output length: {len(ksms_output) if ksms_output else 0}")
        if ksms_output:
            self.logger.info(f"KSMS output preview: {ksms_output[:200]}...")
        
        if ksms_output:
            try:
                ksms_data = json.loads(ksms_output.strip())
                self.logger.debug(f"KSMS output parsed successfully: {len(ksms_data.get('routers', []))} routers")
                return ksms_data
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse KSMS JSON output: {e}")
                self.logger.error(f"KSMS stdout: {ksms_output[:500]}...")
                raise RuntimeError(f"Invalid JSON from KSMS: {e}")
        else:
            # Handle failed command like MultiServiceTester - don't throw exception, return error result
            self.logger.error("KSMS command failed - tsimsh_exec returned None")
            return {
                "error": "KSMS command failed", 
                "routers": []  # Empty routers list to prevent further errors
            }
    
    
    def _convert_to_service_format(self, ksms_results: Dict, params: Dict) -> Dict[str, Any]:
        """Convert KSMS router-based format to service-based format
        
        CRITICAL: Transform structure for PDF compatibility
        KSMS: routers[].services[] -> Service format: tests[] with router info
        
        Args:
            ksms_results: Raw KSMS results (router-based)
            params: Job parameters
            
        Returns:
            Results in service-based format expected by PDF generator
        """
        # Check if KSMS had an error
        if 'error' in ksms_results:
            self.logger.warning(f"KSMS had error: {ksms_results['error']}")
            # Return minimal result structure for error case
            return {
                'summary': {'total_tests': 0, 'successful': 0, 'failed': 0, 'overall_status': 'ERROR'},
                'tests': [],
                'ksms_source': True,
                'analysis_mode': 'quick',
                'error': ksms_results['error']
            }
        
        # Extract info from KSMS results
        source_ip = ksms_results.get('source', params['source_ip'])
        dest_ip = ksms_results.get('destination', params['dest_ip'])
        
        tests = []
        summary_stats = {'total_tests': 0, 'successful': 0, 'failed': 0}
        
        # Transform: for each router's services, create test entries
        for router in ksms_results.get('routers', []):
            router_name = router['name']
            router_iface = router.get('iface', 'unknown')
            
            for service in router.get('services', []):
                port = service['port']
                protocol = service['protocol']
                result = service['result']  # YES/NO/UNKNOWN
                
                # Map KSMS result to service format
                if result == 'YES':
                    status = 'OK'
                    summary_stats['successful'] += 1
                else:  # NO or UNKNOWN
                    status = 'FAIL'
                    summary_stats['failed'] += 1
                
                summary_stats['total_tests'] += 1
                
                # Create test entry in service format
                test_entry = {
                    'source_host': f"source-ksms-{router_name}",
                    'source_ip': source_ip,
                    'source_port': 'ephemeral',  # KSMS doesn't track specific ports
                    'protocol': protocol,
                    'destination_host': f"dest-ksms-{router_name}",
                    'destination_ip': dest_ip,
                    'destination_port': port,
                    'via_router': router_name,
                    'incoming_interface': router_iface,
                    'outgoing_interface': router_iface,
                    'status': status,
                    'message': f"KSMS result: {result}",
                    'ksms_original_result': result  # Keep original for reference
                }
                
                tests.append(test_entry)
        
        # Determine overall status
        if summary_stats['failed'] == 0:
            overall_status = 'OK'
        elif summary_stats['successful'] == 0:
            overall_status = 'FAIL'
        else:
            overall_status = 'PARTIAL'
        
        summary_stats['overall_status'] = overall_status
        
        service_format = {
            'summary': summary_stats,
            'tests': tests,
            'ksms_source': True,  # Flag to indicate this came from KSMS
            'analysis_mode': 'quick'
        }
        
        self.logger.info(f"Converted KSMS results: {summary_stats['total_tests']} tests, "
                        f"{summary_stats['successful']} OK, {summary_stats['failed']} FAIL")
        
        return service_format
    
    def _generate_summary_pdf(self, service_results: Dict, params: Dict, ksms_results: Dict) -> Dict[str, Any]:
        """Generate summary PDF using existing PDF generation infrastructure
        
        Args:
            service_results: Results in service-based format
            params: Job parameters
            
        Returns:
            PDF generation result
        """
        run_id = params['run_id']
        run_dir = Path(params.get('run_dir', f'/dev/shm/tsim/runs/{run_id}'))
        run_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Prepare results for PDF script
            results_list = self._prepare_results_for_pdf_script(service_results)
            
            # Write results to file (required by PDF script)
            results_file = run_dir / f"{run_id}_results.json"
            with open(results_file, 'w') as f:
                json.dump(service_results, f, indent=2)
            
            # Extract unique services for form data
            unique_services = []
            seen_services = set()
            for test in service_results.get('tests', []):
                service_key = (test['destination_port'], test['protocol'])
                if service_key not in seen_services:
                    unique_services.append({
                        'port': test['destination_port'],
                        'protocol': test['protocol'],
                        'port_protocol': f"{test['destination_port']}/{test['protocol']}"
                    })
                    seen_services.add(service_key)
            
            # Write form data (required by PDF script)
            from datetime import datetime
            form_data = {
                'source_ip': params['source_ip'],
                'dest_ip': params['dest_ip'], 
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'session_id': run_id,
                'analysis_mode': 'quick',
                'run_id': run_id
            }
            form_data_file = run_dir / f"{run_id}_form.json"
            with open(form_data_file, 'w') as f:
                json.dump(form_data, f, indent=2)
            
            # Generate summary PDF using existing script  
            # Use _report.pdf name to match what the system expects
            summary_pdf = run_dir / f"{run_id}_report.pdf"
            
            try:
                # Create individual service result files in MultiServiceTester format
                # This is what the PDF script expects
                results_list = []
                unique_services = set()
                
                # Extract services from KSMS results  
                for test in service_results.get('tests', []):
                    port = test['destination_port']
                    protocol = test['protocol']
                    service_key = (port, protocol)
                    
                    if service_key not in unique_services:
                        unique_services.add(service_key)
                        
                        # Create individual result file in MultiServiceTester format
                        service_file = run_dir / 'results' / f"{port}_{protocol}_results.json"
                        service_data = self._create_multiservicetester_format(
                            ksms_results, port, protocol, params
                        )
                        
                        with open(service_file, 'w') as f:
                            json.dump(service_data, f, indent=2)
                        
                        results_list.append({
                            'port': port,
                            'protocol': protocol,
                            'file': str(service_file)
                        })
                
                # Write results list
                results_list_file = run_dir / f"{run_id}_results_list.json"
                with open(results_list_file, 'w') as f:
                    json.dump(results_list, f, indent=2)
                
                # Use installed PDF generation script
                import subprocess
                cmd = [
                    'generate_summary_page_reportlab.py',
                    '--form-data', str(form_data_file),
                    '--results', str(results_list_file),
                    '--output', str(summary_pdf)
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode != 0:
                    raise RuntimeError(f"PDF generation failed: {result.stderr}")
                
                if summary_pdf.exists():
                    self.logger.info(f"Generated summary PDF: {summary_pdf}")
                    return {
                        'success': True,
                        'pdf_path': str(summary_pdf),
                        'pdf_size': summary_pdf.stat().st_size
                    }
                else:
                    raise RuntimeError("PDF file was not created")
                    
            except ImportError as e:
                self.logger.error(f"PDF generation script import failed: {e}")
                raise RuntimeError(f"PDF generation not available: {e}")
        
        except Exception as e:
            self.logger.error(f"PDF generation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'pdf_path': None
            }
    
    def _prepare_results_for_pdf_script(self, service_results: Dict) -> List[Dict]:
        """Convert service results to format expected by PDF generation scripts
        
        Args:
            service_results: Service-based results
            
        Returns:
            List of results in format expected by generate_summary_page_reportlab
        """
        results_list = []
        
        for test in service_results.get('tests', []):
            results_list.append({
                'port': test['destination_port'],
                'protocol': test['protocol'],
                'router': test['via_router'],
                'status': test['status'],
                'file': None  # KSMS doesn't generate per-service files
            })
        
        return results_list
    
    def _create_ksms_summary_pdf(self, output_file: str, form_data: Dict, service_results: Dict):
        """Create KSMS-specific summary PDF using ReportLab
        
        Args:
            output_file: Output PDF file path
            form_data: Form data with source/destination info
            service_results: Converted service-based results
        """
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from datetime import datetime
            
            # Create the PDF document
            doc = SimpleDocTemplate(output_file, pagesize=A4,
                                   rightMargin=72, leftMargin=72,
                                   topMargin=72, bottomMargin=72)
            
            # Build the document content
            story = []
            styles = getSampleStyleSheet()
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                alignment=TA_CENTER,
                spaceAfter=30
            )
            
            story.append(Paragraph("Network Service Reachability Analysis", title_style))
            story.append(Paragraph("Quick Analysis Summary", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            # Test parameters
            story.append(Paragraph("Test Parameters", styles['Heading3']))
            params_data = [
                ['Source IP:', form_data.get('source_ip', 'N/A')],
                ['Destination IP:', form_data.get('dest_ip', 'N/A')],
                ['Analysis Mode:', form_data.get('analysis_mode', 'quick')],
                ['Test Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                ['Services Tested:', str(len(form_data.get('services', [])))]
            ]
            
            params_table = Table(params_data, colWidths=[2*inch, 3*inch])
            params_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ]))
            
            story.append(params_table)
            story.append(Spacer(1, 20))
            
            # Summary statistics
            summary = service_results.get('summary', {})
            story.append(Paragraph("Test Summary", styles['Heading3']))
            
            summary_data = [
                ['Total Tests:', str(summary.get('total_tests', 0))],
                ['Successful:', str(summary.get('successful', 0))],
                ['Failed:', str(summary.get('failed', 0))],
                ['Overall Status:', summary.get('overall_status', 'UNKNOWN')]
            ]
            
            summary_table = Table(summary_data, colWidths=[2*inch, 3*inch])
            summary_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ]))
            
            story.append(summary_table)
            story.append(Spacer(1, 20))
            
            # Service results table
            story.append(Paragraph("Service Test Results", styles['Heading3']))
            
            # Create table headers
            table_data = [['Port', 'Protocol', 'Router', 'Status', 'KSMS Result']]
            
            # Group results by service for cleaner display
            service_groups = {}
            for test in service_results.get('tests', []):
                service_key = (test['destination_port'], test['protocol'])
                if service_key not in service_groups:
                    service_groups[service_key] = []
                service_groups[service_key].append(test)
            
            # Add rows for each unique service
            for (port, protocol), tests in sorted(service_groups.items()):
                # Show results from all routers for this service
                for i, test in enumerate(tests):
                    port_display = str(port) if i == 0 else ''  # Only show port on first row
                    protocol_display = protocol if i == 0 else ''  # Only show protocol on first row
                    
                    status_color = colors.green if test['status'] == 'OK' else colors.red
                    table_data.append([
                        port_display,
                        protocol_display,
                        test.get('via_router', 'N/A'),
                        test['status'],
                        test.get('ksms_original_result', 'N/A')
                    ])
            
            # Create and style the table
            results_table = Table(table_data, colWidths=[0.8*inch, 0.8*inch, 1.5*inch, 0.8*inch, 1.1*inch])
            
            table_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),  # Header
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),    # Header bold
            ]
            
            # Add row coloring based on status
            for i, row in enumerate(table_data[1:], 1):  # Skip header
                if len(row) > 3:  # Ensure we have status column
                    if row[3] == 'OK':
                        table_style.append(('TEXTCOLOR', (3, i), (3, i), colors.green))
                    elif row[3] == 'FAIL':
                        table_style.append(('TEXTCOLOR', (3, i), (3, i), colors.red))
            
            results_table.setStyle(TableStyle(table_style))
            story.append(results_table)
            
            # Add footer note
            story.append(Spacer(1, 30))
            footer_text = """
            <i>This is a quick analysis summary generated using KSMS (Kernel-Space Multi-Service) testing.
            For detailed per-service analysis with iptables rule detection, please run a detailed analysis.</i>
            """
            story.append(Paragraph(footer_text, styles['Normal']))
            
            # Build the PDF
            doc.build(story)
            self.logger.info(f"KSMS summary PDF created: {output_file}")
            
        except ImportError as e:
            self.logger.error(f"ReportLab not available for PDF generation: {e}")
            raise RuntimeError(f"PDF generation requires ReportLab: {e}")
        except Exception as e:
            self.logger.error(f"Failed to create KSMS summary PDF: {e}")
            raise
    
    def validate_ksms_results(self, results: Dict) -> bool:
        """Sanity check KSMS results before using as hints
        
        Args:
            results: KSMS results dictionary
            
        Returns:
            True if results appear valid
        """
        if not isinstance(results, dict):
            return False
        
        if 'routers' not in results:
            return False
        
        routers = results['routers']
        if not isinstance(routers, list) or len(routers) == 0:
            return False
        
        # Check each router has required fields
        for router in routers:
            if not isinstance(router, dict):
                return False
            if 'name' not in router or 'services' not in router:
                return False
            
            services = router['services']
            if not isinstance(services, list):
                return False
            
            # Check each service has required fields
            for service in services:
                if not isinstance(service, dict):
                    return False
                required_fields = ['port', 'protocol', 'result']
                if not all(field in service for field in required_fields):
                    return False
                if service['result'] not in ['YES', 'NO', 'UNKNOWN']:
                    return False
        
        return True
    
    def create_blocking_allowing_map(self, ksms_results: Dict) -> Dict[str, Dict]:
        """Convert KSMS results to hints for rule analyzer
        
        Args:
            ksms_results: Raw KSMS results
            
        Returns:
            Mapping of service->router->hint for detailed analysis
        """
        hints_map = {}
        
        for router in ksms_results.get('routers', []):
            router_name = router['name']
            
            for service in router.get('services', []):
                port = service['port']
                protocol = service['protocol']
                result = service['result']
                
                service_key = f"{port}/{protocol}"
                
                if service_key not in hints_map:
                    hints_map[service_key] = {}
                
                # Convert KSMS result to hints
                if result == 'YES':
                    hints_map[service_key][router_name] = {
                        'allowing': True,
                        'blocking': False
                    }
                elif result == 'NO':
                    hints_map[service_key][router_name] = {
                        'allowing': False,
                        'blocking': True
                    }
                else:  # UNKNOWN
                    hints_map[service_key][router_name] = {
                        'allowing': False,
                        'blocking': False
                    }
        
        return hints_map
    
    def _setup_source_hosts(self, params: Dict[str, Any], run_id: str, log_progress) -> List[str]:
        """Setup source hosts from trace file
        
        Args:
            params: Parameters including trace_file
            run_id: Run ID for logging
            log_progress: Progress logging function
            
        Returns:
            List of routers where source hosts were created
        """
        routers = []
        
        # Get routers from trace file
        trace_file = params.get('trace_file')
        if trace_file:
            try:
                with open(trace_file, 'r') as f:
                    trace_data = json.load(f)
                
                # Extract routers from path (only router hops)
                path = trace_data.get('path', [])
                routers = [hop['name'] for hop in path if hop.get('is_router')]
                
            except Exception as e:
                self.logger.error(f"Failed to read trace file {trace_file}: {e}")
                return []
        
        if not routers:
            self.logger.warning(f"No routers found in trace for {run_id}")
            return []
        
        source_ip = params['source_ip']
        
        # Add source hosts to routers (1-based indexing like MultiServiceTester)
        created_hosts = []
        for i, router in enumerate(routers, 1):
            src_host_name = f"source-{i}"
            
            # Log individual host creation step
            log_progress(f'PHASE2_host_{i}', f'Creating source host {src_host_name} on {router.split(".")[0]}')
            
            # Add source host to this router
            self.logger.debug(f"Adding source host {src_host_name} to router {router}")
            result = tsimsh_exec(
                f"host add --name {src_host_name} --primary-ip {source_ip}/24 --connect-to {router} --no-delay",
                capture_output=True, verbose=1
            )
            
            if result is not None:
                created_hosts.append(src_host_name)
            else:
                self.logger.warning(f"Failed to create source host {src_host_name} on {router}")
        
        self.logger.info(f"Created {len(created_hosts)} source hosts for KSMS scan")
        return routers
    
    def _cleanup_source_hosts(self, routers: List[str], run_id: str):
        """Remove created source hosts
        
        Args:
            routers: List of routers where hosts were created
            run_id: Run ID for logging
        """
        for i, router in enumerate(routers, 1):
            src_host_name = f"source-{i}"
            
            self.logger.debug(f"Removing source host {src_host_name}")
            result = tsimsh_exec(
                f"host remove --name {src_host_name} --force",
                capture_output=True, verbose=1
            )
            
            if result is None:
                self.logger.warning(f"Failed to remove source host {src_host_name}")
        
        self.logger.info(f"Cleaned up source hosts for {run_id}")
    
    def _create_multiservicetester_format(self, ksms_results: Dict, port: int, protocol: str, params: Dict) -> Dict:
        """Create MultiServiceTester-compatible format for individual service
        
        Args:
            ksms_results: Raw KSMS results from ksms_tester
            port: Service port
            protocol: Service protocol  
            params: Job parameters
            
        Returns:
            MultiServiceTester-compatible result structure
        """
        import time
        from datetime import datetime
        
        # Extract router results for this specific service
        router_tests = []
        service_tests = []
        
        for router in ksms_results.get('routers', []):
            router_name = router['name']
            
            for service in router.get('services', []):
                if service['port'] == port and service['protocol'] == protocol:
                    result = service['result']  # YES/NO/UNKNOWN
                    
                    # Create traceroute test entry (fake for KSMS)
                    router_tests.append({
                        "source": {
                            "namespace": f"source-{len(router_tests)+1}",
                            "namespace_type": "host", 
                            "ip": params['source_ip']
                        },
                        "destination": {
                            "namespace": f"destination-{len(router_tests)+1}",
                            "namespace_type": "host",
                            "ip": params['dest_ip']  
                        },
                        "router": router_name,
                        "test_type": "TRACEROUTE",
                        "success": True,  # Always true for KSMS (no actual traceroute)
                        "summary": "TRACEROUTE successful"
                    })
                    
                    # Create service test entry
                    service_tests.append({
                        "source_host": f"source-{len(service_tests)+1}",
                        "source_ip": params['source_ip'],
                        "source_port": "ephemeral", 
                        "protocol": protocol,
                        "destination_host": f"destination-{len(service_tests)+1}",
                        "destination_ip": params['dest_ip'],
                        "destination_port": port,
                        "via_router": router_name,
                        "incoming_interface": router.get('iface', 'unknown'),
                        "outgoing_interface": router.get('iface', 'unknown'),
                        "status": "OK" if result == "YES" else "FAIL",
                        "message": f"KSMS result: {result}"
                    })
        
        # Create MultiServiceTester-compatible structure
        successful = len([t for t in service_tests if t['status'] == 'OK'])
        failed = len([t for t in service_tests if t['status'] == 'FAIL'])
        
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0.0",
            "summary": {
                "source_ip": params['source_ip'],
                "source_port": "ephemeral",
                "destination_ip": params['dest_ip'], 
                "destination_port": str(port),
                "protocol": protocol
            },
            "setup_status": {
                "source_host_added": True,
                "destination_host_added": True, 
                "service_started": True
            },
            "reachability_tests": {
                "ping": {
                    "result": None,
                    "return_code": None
                },
                "traceroute": {
                    "result": {
                        "summary": {
                            "total_tests": len(router_tests),
                            "passed": len(router_tests),  # All pass for KSMS
                            "failed": 0,
                            "pass_rate": 100.0,
                            "all_passed": True
                        },
                        "tests": router_tests
                    },
                    "return_code": 0
                },
                "service": {
                    "result": {
                        "summary": {
                            "total_tests": len(service_tests),
                            "successful": successful,
                            "failed": failed,
                            "overall_status": "OK" if failed == 0 else ("PARTIAL" if successful > 0 else "FAIL")
                        },
                        "tests": service_tests
                    },
                    "return_code": 0
                }
            }
        }
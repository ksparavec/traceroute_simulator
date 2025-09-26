#!/usr/bin/env -S python3 -B -u
"""
Generate a summary page for multi-service test results using ReportLab.
This creates the first page of the PDF showing a summary table of all services tested.
"""

import json
import sys
import os
import argparse
from typing import Dict, List, Tuple, Any
from datetime import datetime

# ReportLab imports
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_ksms_summary(ksms_results: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    """Extract summary information from KSMS results."""
    summary = []
    routers = []
    traceroute_status = {}  # Empty for KSMS (no traceroute)
    
    # Extract routers and services from KSMS format
    for router_data in ksms_results.get('routers', []):
        router_name = router_data['name']
        if router_name not in routers:
            routers.append(router_name)
        
        for service_data in router_data.get('services', []):
            port = service_data['port']
            protocol = service_data['protocol']
            result = service_data['result']  # YES/NO/UNKNOWN
            
            # Find or create service summary
            service_summary = None
            for s in summary:
                if s['port'] == port and s['protocol'] == protocol:
                    service_summary = s
                    break
            
            if not service_summary:
                service_summary = {
                    'port': port,
                    'protocol': protocol,
                    'router_results': {}
                }
                summary.append(service_summary)
            
            # Convert KSMS result to status
            status = 'PASS' if result == 'YES' else 'FAIL'
            service_summary['router_results'][router_name] = status
    
    return summary, routers, traceroute_status


def extract_test_summary(results_files: List[Tuple[int, str, str]]) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, str]]:
    """Extract summary information from all result files."""
    summary = []
    routers = []  # Keep as ordered list instead of set
    routers_seen = set()
    traceroute_status = {}  # Store traceroute status per router
    
    # Get traceroute results from first file (they're the same for all services)
    if results_files:
        first_result = load_json_file(results_files[0][2])
        reachability_tests = first_result.get('reachability_tests', {})
        traceroute_test = reachability_tests.get('traceroute', {})
        tr_result = traceroute_test.get('result', {})
        
        # Get per-router traceroute status from tests
        if tr_result:
            for test in tr_result.get('tests', []):
                router_name = test.get('router', '')
                if router_name and test.get('success', False):
                    traceroute_status[router_name] = 'PASS'
                elif router_name:
                    traceroute_status[router_name] = 'FAIL'
    
    for port, protocol, result_file in results_files:
        # Load result file
        result = load_json_file(result_file)
        
        # Extract connectivity test results
        service_summary = {
            'port': port,
            'protocol': protocol.upper(),
            'router_status': {}
        }
        
        # Get connectivity test results - check both locations for compatibility
        # First try the formatted location (reachability_tests.service.result)
        reachability_tests = result.get('reachability_tests', {})
        service_test = reachability_tests.get('service', {})
        conn_test = service_test.get('result', {})
        
        # Fall back to original location if not found
        if not conn_test:
            conn_test = result.get('connectivity_test', {})
        
        tests = conn_test.get('tests', [])
        
        # Determine status for each router - preserve order from tests
        for test in tests:
            if 'via_router' in test:
                router = test['via_router']
                # Preserve order - only add if not seen before
                if router not in routers_seen:
                    routers.append(router)
                    routers_seen.add(router)
                status = test.get('status', '')
                
                if status == 'OK':
                    service_summary['router_status'][router] = 'ALLOWED'
                elif status in ['FAIL', 'TIMEOUT', 'ERROR']:
                    service_summary['router_status'][router] = 'BLOCKED'
                else:
                    service_summary['router_status'][router] = 'UNKNOWN'
        
        summary.append(service_summary)
    
    return summary, routers, traceroute_status


def create_summary_page_from_data(output_file: str, form_data: Dict[str, Any],
                                 services_summary: List[Dict[str, Any]], 
                                 routers: List[str], traceroute_status: Dict[str, str]) -> None:
    """Create the summary page PDF from extracted data using ReportLab."""
    
    # Create the PDF document
    doc = SimpleDocTemplate(output_file, pagesize=A4,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=72)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Get styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=6,
        alignment=TA_CENTER
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#34495E'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=12,
        spaceBefore=20
    )
    
    # Title
    elements.append(Paragraph('Traceroute Simulator v2.0.0', title_style))
    elements.append(Paragraph('Network Reachability Test Report', subtitle_style))
    
    # Test Information Section
    elements.append(Paragraph('Test Information', section_style))
    
    # Create info table data
    source_ip = form_data.get('source_ip', 'N/A')
    dest_ip = form_data.get('dest_ip', 'N/A')
    timestamp = form_data.get('timestamp', 'N/A')
    session_id = form_data.get('session_id', form_data.get('run_id', 'N/A'))
    services_str = ', '.join([f"{s['port']}/{s['protocol']}" for s in services_summary])
    firewall_names = ', '.join([router.split('.')[0] for router in routers])
    
    info_data = [
        ['Source IP:', source_ip],
        ['Destination IP:', dest_ip],
        ['Test Date/Time:', timestamp],
        ['Session ID:', session_id],
        ['Services Tested:', services_str],
        ['Firewalls:', firewall_names]
    ]
    
    # Create info table - let ReportLab handle column widths automatically
    info_table = Table(info_data)
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#555')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333')),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    
    elements.append(info_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # Test Results Section
    elements.append(Paragraph('Test Results', section_style))
    
    # Create results table data
    table_headers = ['Service'] + [router.split('.')[0] for router in routers]
    table_data = [table_headers]
    
    # Add traceroute row (skip for KSMS quick analysis)
    analysis_mode = form_data.get('analysis_mode', 'detailed')
    if analysis_mode != 'quick':
        traceroute_row = ['TRACEROUTE']
        for router in routers:
            status = traceroute_status.get(router, 'N/A')
            traceroute_row.append(status)
        table_data.append(traceroute_row)
    
    # Add service rows
    for service in services_summary:
        row = [f"{service['port']}/{service['protocol']}"]
        for router in routers:
            status = service['router_status'].get(router, 'N/A')
            row.append(status)
        table_data.append(row)
    
    # Let ReportLab auto-calculate column widths based on content
    # Only set minimum width for first column
    results_table = Table(table_data)  # Auto-size all columns
    
    # Build table style dynamically
    table_style_commands = [
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgray),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # Service header
        ('ALIGN', (1, 0), (-1, 0), 'CENTER'),  # Router headers
        
        # Data rows
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Service column
        ('FONTNAME', (1, 1), (-1, -1), 'Helvetica-Bold'),  # Status cells
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # Service column
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),  # Status columns
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        
        # Service column background
        ('BACKGROUND', (0, 1), (0, -1), colors.lightgrey),
        
        # Grid
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.white]),
    ]
    
    # Color cells based on status
    for row_idx, row in enumerate(table_data[1:], start=1):  # Skip header
        for col_idx, cell in enumerate(row[1:], start=1):  # Skip service column
            if cell == 'ALLOWED' or cell == 'PASS':
                table_style_commands.append(
                    ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.lightgreen)
                )
            elif cell == 'BLOCKED' or cell == 'FAIL':
                table_style_commands.append(
                    ('BACKGROUND', (col_idx, row_idx), (col_idx, row_idx), colors.HexColor('#FFA07A'))
                )
    
    results_table.setStyle(TableStyle(table_style_commands))
    elements.append(results_table)
    
    # Footer (only for detailed analysis)
    analysis_mode = form_data.get('analysis_mode', 'detailed')
    if analysis_mode != 'quick':
        elements.append(Spacer(1, 0.5*inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#7F8C8D'),
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )
        elements.append(Paragraph('Detailed analysis for each service follows on subsequent pages', footer_style))
    
    # Build PDF
    doc.build(elements)


def create_summary_page(output_file: str, form_data: Dict[str, Any], 
                       results_files: List[Tuple[int, str, str]]) -> None:
    """Create the summary page PDF using ReportLab (MultiServiceTester format)."""
    
    # Extract summary from all results
    services_summary, routers, traceroute_status = extract_test_summary(results_files)
    
    # Create PDF from extracted data
    create_summary_page_from_data(output_file, form_data, services_summary, routers, traceroute_status)


def main():
    parser = argparse.ArgumentParser(description='Generate summary page for multi-service test results')
    parser.add_argument('--form-data', required=True, help='JSON file with form data')
    parser.add_argument('--results', required=True, help='JSON file with list of result files')
    parser.add_argument('--output', required=True, help='Output PDF file')
    
    args = parser.parse_args()
    
    # Load form data
    form_data = load_json_file(args.form_data)
    
    # Load list of result files
    results_info = load_json_file(args.results)
    
    # Check if this is KSMS format (single file with ksms_results)
    if len(results_info) == 1 and 'file' in results_info[0]:
        result_data = load_json_file(results_info[0]['file'])
        if 'ksms_results' in result_data:
            # This is KSMS format - extract data directly
            ksms_results = result_data['ksms_results']
            services_summary, routers, traceroute_status = extract_ksms_summary(ksms_results)
            create_summary_page_from_data(args.output, form_data, services_summary, routers, traceroute_status)
            print(f"KSMS Summary page generated: {args.output}")
            return
    
    # Standard MultiServiceTester format
    results_files = []
    for item in results_info:
        results_files.append((item['port'], item['protocol'], item['file']))
    
    # Generate summary page
    create_summary_page(args.output, form_data, results_files)
    
    print(f"Summary page generated: {args.output}")


if __name__ == '__main__':
    main()
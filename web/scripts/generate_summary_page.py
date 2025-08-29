#!/usr/bin/env -S python3 -B -u
"""
Generate a summary page for multi-service test results.
This creates the first page of the PDF showing a summary table of all services tested.
"""

import json
import sys
import os
import argparse
from typing import Dict, List, Tuple, Any

# Set matplotlib to use non-interactive backend before importing pyplot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def extract_test_summary(results_files: List[Tuple[int, str, str]]) -> List[Dict[str, Any]]:
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
    
    return summary, routers, traceroute_status  # Return ordered list and traceroute status


def create_summary_page(output_file: str, form_data: Dict[str, Any], 
                       results_files: List[Tuple[int, str, str]]) -> None:
    """Create the summary page PDF with A4 portrait format."""
    
    # Extract summary from all results
    services_summary, routers, traceroute_status = extract_test_summary(results_files)
    
    # Create figure with A4 portrait dimensions (8.27 x 11.69 inches)
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.patch.set_facecolor('white')
    
    # Define the middle 2/3 area (1/6 margin on each side)
    left_margin = 1/6
    right_margin = 1 - 1/6
    content_width = right_margin - left_margin
    
    # Title - Traceroute Simulator with version (moved down and more spaced)
    plt.figtext(0.5, 0.90, 'Traceroute Simulator v2.0.0', 
                fontsize=24, fontweight='bold', ha='center', color='#2C3E50')
    plt.figtext(0.5, 0.87, 'Network Reachability Test Report', 
                fontsize=16, fontweight='bold', ha='center', color='#34495E')
    
    # Test Information Section with better spacing (adjusted for new title position)
    y_pos = 0.80  # Moved up from 0.82
    section_x = left_margin + 0.05
    
    plt.figtext(section_x, y_pos, 'Test Information', fontsize=14, fontweight='bold', color='#2C3E50')
    y_pos -= 0.025  # Reduced from 0.03
    
    # Display test metadata with better formatting
    source_ip = form_data.get('source_ip', 'N/A')
    dest_ip = form_data.get('dest_ip', 'N/A')
    timestamp = form_data.get('timestamp', 'N/A')
    session_id = form_data.get('session_id', form_data.get('run_id', 'N/A'))
    
    # Create two-column layout for test information with proper spacing
    info_x = section_x + 0.02
    label_x_offset = 0.18  # Increased offset for labels to prevent overlap
    
    plt.figtext(info_x, y_pos, 'Source IP:', fontsize=11, fontweight='bold', color='#555')
    plt.figtext(info_x + label_x_offset, y_pos, source_ip, fontsize=11, color='#333')
    y_pos -= 0.03
    
    plt.figtext(info_x, y_pos, 'Destination IP:', fontsize=11, fontweight='bold', color='#555')
    plt.figtext(info_x + label_x_offset, y_pos, dest_ip, fontsize=11, color='#333')
    y_pos -= 0.03
    
    plt.figtext(info_x, y_pos, 'Test Date/Time:', fontsize=11, fontweight='bold', color='#555')
    plt.figtext(info_x + label_x_offset, y_pos, timestamp, fontsize=11, color='#333')
    y_pos -= 0.03
    
    plt.figtext(info_x, y_pos, 'Session ID:', fontsize=11, fontweight='bold', color='#555')
    # Get session ID from run_id if session_id is N/A
    if session_id == 'N/A' or not session_id:
        session_id = form_data.get('run_id', 'N/A')
    # Display full session ID on single line with smaller font if needed
    plt.figtext(info_x + label_x_offset, y_pos, session_id, 
                fontsize=9, color='#333', family='monospace')
    y_pos -= 0.03
    
    # Services tested
    services_str = ', '.join([f"{s['port']}/{s['protocol']}" for s in services_summary])
    plt.figtext(info_x, y_pos, 'Services Tested:', fontsize=11, fontweight='bold', color='#555')
    plt.figtext(info_x + label_x_offset, y_pos, services_str, fontsize=11, color='#333')
    y_pos -= 0.03
    
    # Firewalls
    firewall_names = ', '.join([router.split('.')[0] for router in routers])
    plt.figtext(info_x, y_pos, 'Firewalls:', fontsize=11, fontweight='bold', color='#555')
    plt.figtext(info_x + label_x_offset, y_pos, firewall_names, fontsize=11, color='#333')
    y_pos -= 0.05  # Increased spacing before Test Results section
    
    # Results Summary Section
    plt.figtext(section_x, y_pos, 'Test Results', fontsize=14, fontweight='bold', color='#2C3E50')
    y_pos -= 0.025  # Match the spacing used after Test Information title
    
    # Create table data with headers as first row (like service pages do)
    table_headers = ['Service']
    for router in routers:
        # Take only the hostname part (before first dot)
        hostname = router.split('.')[0]
        table_headers.append(hostname)
    
    # Include headers as first row of data
    table_data = [table_headers]
    
    # Add traceroute as second row
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
    
    # Create table axes - properly left-aligned with text
    # Calculate table dimensions - adjust width based on number of routers
    num_routers = len(routers)
    # Base width plus additional width per router
    table_width = min(0.35 + num_routers * 0.10, 0.55)  # Back to original width
    table_height = 0.08 + len(table_data) * 0.05  # Regular height since no two-line text
    table_y = y_pos - table_height  # Position table directly below "Test Results" without extra gap
    table_x = info_x - 0.02  # Align with actual text start position (same as info_x)
    
    ax = fig.add_axes([table_x, table_y, table_width, table_height])
    ax.axis('tight')
    ax.axis('off')
    
    # Define colors for cell backgrounds to match service pages
    cell_colors = []
    
    for i, row in enumerate(table_data):
        if i == 0:  # Header row
            row_colors = ['darkgray'] * len(row)  # All headers dark gray
        else:
            row_colors = ['lightgray']  # Light gray for service/traceroute name column
            
            # Color router cells based on content
            for cell in row[1:]:
                if cell == 'ALLOWED':
                    row_colors.append('lightgreen')  # Same green as service pages
                elif cell == 'BLOCKED':
                    row_colors.append('lightcoral')  # Same red as service pages
                elif cell == 'PASS':
                    row_colors.append('lightgreen')  # Green for traceroute pass
                elif cell == 'FAIL':
                    row_colors.append('lightcoral')  # Red for traceroute fail
                else:
                    row_colors.append('white')  # White for unknown
        cell_colors.append(row_colors)
    
    # Create the table with better styling (headers included in cellText like service pages)
    table = ax.table(cellText=table_data,
                     cellLoc='left',  # Left alignment for text
                     loc='top',  # Changed from 'center' to 'top' for top vertical alignment
                     cellColours=cell_colors)
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    
    # Make table taller and add more padding to match service pages
    table.scale(1, 2.0)  # Match service page row height
    
    # Style the table cells to match service pages exactly
    for (i, j), cell in table.get_celld().items():
        cell.set_linewidth(0.5)
        cell.set_edgecolor('gray')
        cell.PAD = 0.1  # Match service page padding
        
        if i == 0:  # Header row - all columns
            cell.set_facecolor('darkgray')  # Dark gray for all headers
            cell.set_edgecolor('gray')
            cell.set_linewidth(0.5)
            # Set text properties for header cells
            cell.set_text_props(weight='bold', color='white', va='top')
            if j > 0:  # Center-align router columns
                cell.set_text_props(ha='center')
        elif j == 0:  # Service column data cells (non-header)
            cell.set_text_props(weight='bold', ha='left', va='top')
            cell.set_facecolor('lightgray')
        else:
            # Style router status cells based on content - match service pages exactly
            text = cell.get_text().get_text()
            if text in ['ALLOWED', 'BLOCKED', 'PASS', 'FAIL']:
                cell.set_text_props(weight='bold', ha='center', va='top')
            else:
                cell.set_text_props(va='top')  # Top align even for empty cells
    
    # Footer with separator line
    footer_y = 0.08
    # Draw a subtle separator line
    ax_line = fig.add_axes([left_margin, footer_y + 0.01, content_width, 0.001])
    ax_line.axhline(y=0, color='#BDC3C7', linewidth=1)
    ax_line.axis('off')
    
    plt.figtext(0.5, footer_y - 0.01, 'Detailed analysis for each service follows on subsequent pages',
                fontsize=10, ha='center', style='italic', color='#7F8C8D')
    
    # Save the figure with proper PDF settings
    plt.savefig(output_file, format='pdf', 
                facecolor='white',
                edgecolor='none',
                bbox_inches=None,  # Don't use tight - preserve A4 dimensions
                pad_inches=0,
                dpi=300)
    plt.close()


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
    
    # Convert to expected format
    results_files = []
    for item in results_info:
        results_files.append((item['port'], item['protocol'], item['file']))
    
    # Generate summary page
    create_summary_page(args.output, form_data, results_files)
    
    print(f"Summary page generated: {args.output}")


if __name__ == '__main__':
    main()
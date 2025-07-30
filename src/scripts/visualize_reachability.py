#!/usr/bin/env -S python3 -B -u
"""
Visualize Network Reachability Test Results using NetworkX

This script creates a graphical representation of network reachability test results
using NetworkX for graph layout and matplotlib for rendering.

Usage:
    ./visualize_reachability_networkx.py --trace-file trace.json --results-file results.json
    ./visualize_reachability_networkx.py -t trace.json -r results.json -o output.png
"""

import json
import sys
import matplotlib.pyplot as plt
import networkx as nx
# from networkx.drawing.nx_agraph import graphviz_layout
import argparse
from typing import Dict, List, Tuple, Any
import textwrap
try:
    from hyphen import Hyphenator
    from hyphen.textwrap2 import fill, wrap
    PYHYPHEN_AVAILABLE = True
except ImportError:
    PYHYPHEN_AVAILABLE = False


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load JSON data from file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def wrap_text(text: str, width: int = 50) -> List[str]:
    """Wrap text to specified width for table display, returns list of lines."""
    if not text:
        return ['']
    
    # Special handling for rule text - break at logical points
    if '-A FORWARD' in text and '-j ' in text:
        # For iptables rules, break strategically to minimize lines
        # Try to keep the action (-j ACCEPT/DROP) visible
        if len(text) > width:
            # Break before -m if present
            if ' -m ' in text:
                text = text.replace(' -m ', '\n-m ')
            # Or break before -j to keep action visible
            elif ' -j ' in text:
                parts = text.split(' -j ')
                if len(parts) == 2 and len(parts[1]) < 20:  # Short action
                    text = parts[0] + '\n-j ' + parts[1]
    
    # For Default policy, keep it on one line
    if text.startswith('Default policy:'):
        return [text]
    
    # Use PyHyphen if available for better wrapping
    if PYHYPHEN_AVAILABLE:
        try:
            h_en = Hyphenator('en_US')
            lines = wrap(text, width=width, use_hyphenator=h_en)
            return lines
        except:
            # Fallback if hyphenation fails
            pass
    
    # Fallback to standard textwrap - aggressive packing
    wrapper = textwrap.TextWrapper(
        width=width,
        break_long_words=True,  # Allow breaking long words to pack tighter
        break_on_hyphens=True,   # Break on hyphens when needed
        expand_tabs=False,
        replace_whitespace=True,
        drop_whitespace=True
    )
    return wrapper.wrap(text)


def wrap_text_to_string(text: str, width: int = 50) -> str:
    """Wrap text and return as newline-joined string."""
    lines = wrap_text(text, width)
    return '\n'.join(lines)


def extract_path_from_trace(trace_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract path information from trace file."""
    path = []
    
    # Add source host
    path.append({
        'type': 'host',
        'name': 'Source Host',
        'ip': trace_data['source'],
        'port': 'ephemeral',
        'is_source': True,
        'is_destination': False
    })
    
    # Add all nodes from path
    if 'path' in trace_data:
        for hop in trace_data['path']:
            if hop.get('is_router', False):
                path.append({
                    'type': 'router',
                    'name': hop.get('name', 'Unknown'),
                    'ip': hop.get('ip', 'Unknown'),
                    'incoming_interface': hop.get('incoming', ''),
                    'outgoing_interface': hop.get('outgoing', ''),
                    'is_source': False,
                    'is_destination': False
                })
    
    # Add destination host
    path.append({
        'type': 'host',
        'name': 'Destination Host',
        'ip': trace_data['destination'],
        'port': trace_data.get('destination_port', '80'),
        'is_source': False,
        'is_destination': True
    })
    
    return path


def get_packet_analysis(results_data: Dict[str, Any]) -> Dict[str, str]:
    """Extract packet analysis information for each router from results."""
    analysis = {}
    
    # Get router service results
    router_results = results_data.get('router_service_results', {})
    for router, status in router_results.items():
        analysis[router] = status
    
    return analysis


def create_networkx_visualization(trace_data: Dict[str, Any], results_data: Dict[str, Any], output_file: str = None):
    """Create the network path visualization using NetworkX."""
    # Extract information
    path = extract_path_from_trace(trace_data)
    packet_analysis = get_packet_analysis(results_data)
    
    # Create directed graph
    G = nx.DiGraph()
    
    # Add nodes with attributes
    node_labels = {}
    node_colors = []
    node_sizes = []
    
    for i, node in enumerate(path):
        node_id = f"node_{i}"
        G.add_node(node_id)
        
        # Create label with name and IP
        label = f"{node['name']}\n{node['ip']}"
        node_labels[node_id] = label
        
        # Set color based on type
        if node['type'] == 'host':
            node_colors.append('#87CEEB')  # Light blue for all hosts
        else:
            node_colors.append('#FFC107')  # Amber for routers
        
        # Set node size - will be overridden by custom rectangles
        node_sizes.append(1)  # Minimal size since we'll draw custom boxes
    
    # Add edges
    for i in range(len(path) - 1):
        G.add_edge(f"node_{i}", f"node_{i+1}")
    
    # Setup figure - A4 portrait
    fig, ax = plt.subplots(figsize=(8.27, 11.69))
    
    # Calculate hierarchical layout without graphviz
    # Create a simple top-to-bottom layout manually
    pos = {}
    x_center = 0
    
    # Calculate positions with variable spacing
    y_position = 0
    for i, node_id in enumerate(G.nodes()):
        pos[node_id] = (x_center, y_position)
        
        # Determine spacing to next node
        if i < len(path) - 1:
            current_node = path[i]
            next_node = path[i + 1]
            
            # Base spacing
            base_spacing = 120
            
            # Add space for interface boxes
            if current_node['type'] == 'router' and current_node.get('outgoing_interface'):
                base_spacing += 30  # Space for outgoing interface box
            if next_node['type'] == 'router' and next_node.get('incoming_interface'):
                base_spacing += 30  # Space for incoming interface box
            
            y_position -= base_spacing
    
    # Don't draw nodes with NetworkX - we'll draw custom rectangles instead
    # Define box dimensions
    router_width = 250  # Width for routers
    host_width = 187.5  # 25% narrower for hosts
    box_height = 65  # Increased height for better text padding
    interface_box_width = 90  # Increased width for better text padding
    interface_box_height = 30  # Increased height for better text padding
    
    # Draw custom rectangular boxes for each node
    from matplotlib.patches import Rectangle
    interface_positions = {}  # Store interface positions for arrow adjustments
    
    for i, (node_id, (x, y)) in enumerate(pos.items()):
        node = path[i]
        
        # Determine box width based on node type
        if node['type'] == 'host':
            box_width = host_width
        else:
            box_width = router_width
        
        # Draw main rectangle with border
        rect = Rectangle((x - box_width/2, y - box_height/2), 
                        box_width, box_height,
                        facecolor=node_colors[i],
                        edgecolor='black',
                        linewidth=2,
                        alpha=0.9)
        ax.add_patch(rect)
        
        # Draw interface boxes for routers
        if node['type'] == 'router':
            # Incoming interface (top)
            if node.get('incoming_interface'):
                in_rect = Rectangle((x - interface_box_width/2, y + box_height/2), 
                                   interface_box_width, interface_box_height,
                                   facecolor='white',
                                   edgecolor='black',
                                   linewidth=1,
                                   alpha=0.9)
                ax.add_patch(in_rect)
                ax.text(x, y + box_height/2 + interface_box_height/2, 
                       node['incoming_interface'],
                       ha='center', va='center', fontsize=7)
                interface_positions[f"{node_id}_in"] = y + box_height/2 + interface_box_height
            
            # Outgoing interface (bottom)
            if node.get('outgoing_interface'):
                out_rect = Rectangle((x - interface_box_width/2, y - box_height/2 - interface_box_height), 
                                    interface_box_width, interface_box_height,
                                    facecolor='white',
                                    edgecolor='black',
                                    linewidth=1,
                                    alpha=0.9)
                ax.add_patch(out_rect)
                ax.text(x, y - box_height/2 - interface_box_height/2, 
                       node['outgoing_interface'],
                       ha='center', va='center', fontsize=7)
                interface_positions[f"{node_id}_out"] = y - box_height/2 - interface_box_height
    
    # Draw edges manually to control exact positioning
    from matplotlib.patches import FancyArrowPatch
    edge_list = list(G.edges())
    for i, (node1, node2) in enumerate(edge_list):
        x1, y1 = pos[node1]
        x2, y2 = pos[node2]
        
        # Check if nodes have interface boxes
        if f"{node1}_out" in interface_positions:
            arrow_start_y = interface_positions[f"{node1}_out"]
        else:
            arrow_start_y = y1 - box_height/2
            
        if f"{node2}_in" in interface_positions:
            arrow_end_y = interface_positions[f"{node2}_in"]
        else:
            arrow_end_y = y2 + box_height/2
        
        # Add small gap to make arrows shorter
        arrow_gap = 3
        if arrow_start_y > arrow_end_y:
            arrow_start_y -= arrow_gap
            arrow_end_y += arrow_gap
        else:
            arrow_start_y += arrow_gap
            arrow_end_y -= arrow_gap
            
        arrow = FancyArrowPatch((x1, arrow_start_y), (x2, arrow_end_y),
                               arrowstyle='-|>',
                               linewidth=1.5,  # Narrower line
                               color='black',
                               alpha=0.7,
                               mutation_scale=15)  # Smaller arrowhead
        ax.add_patch(arrow)
    
    # Draw labels with smaller font for better padding
    nx.draw_networkx_labels(G, pos,
                           labels=node_labels,
                           font_size=8,
                           font_weight='bold',
                           ax=ax)
    
    # Add service status annotations for routers
    for i, node in enumerate(path):
        if node['type'] == 'router' and node['name'] in packet_analysis:
            node_id = f"node_{i}"
            x, y = pos[node_id]
            status = packet_analysis[node['name']]
            
            # Add text to the right of the node
            if status == 'ALLOWED':
                color = '#4CAF50'
            else:
                color = '#F44336'
            
            # Position text to the right of the router box
            ax.text(x + router_width/2 + 20, y, f"Service {status}",
                    fontsize=14, fontweight='bold',
                    color=color, ha='left', va='center')
    
    # Add title and description
    summary = results_data.get('summary', {})
    title_text = 'Network Service Reachability Report'
    
    # Build source part of description
    source_text = f"Source: {summary.get('source_ip', 'N/A')}"
    source_port = summary.get('source_port', '')
    # Only add source port if it's not ephemeral
    if source_port and source_port.lower() != 'ephemeral':
        source_text += f":{source_port}"
    
    # Build destination part with port and protocol
    dest_text = f"Destination: {summary.get('destination_ip', 'N/A')}:{summary.get('destination_port', 'N/A')}/{summary.get('protocol', 'tcp').upper()}"
    
    param_text = f"{source_text} → {dest_text}"
    
    plt.title(title_text, fontsize=20, fontweight='bold', pad=10)  # Reduced gap
    plt.text(0.5, 0.94, param_text, transform=ax.transAxes,
             ha='center', va='top', fontsize=14)
    
    # Set axis limits to show all content with minimal margins
    x_coords = [pos[node][0] for node in pos]
    y_coords = [pos[node][1] for node in pos]
    
    x_margin = 300  # Horizontal margin for service text
    y_margin = 50   # Minimal vertical margin
    
    # Calculate graph bounds
    graph_height = abs(min(y_coords) - max(y_coords)) + box_height
    graph_lowest_y = min(y_coords) - box_height/2 - y_margin
    graph_highest_y = max(y_coords) + box_height/2 + y_margin
    
    # Position graph at top of page with proper spacing from description
    # Description is at y=0.94, so graph starts lower
    top_margin = 250  # Space from description to first node
    
    # Calculate space needed for table
    table_rows = 1  # Header row
    
    # Count ping test rows
    ping_tests = results_data.get('reachability_tests', {}).get('ping', {}).get('result', {}).get('tests', [])
    if ping_tests:
        table_rows += 1  # Overall summary
        table_rows += len(ping_tests)  # Individual router results
    
    # Count MTR test rows
    mtr_tests = results_data.get('reachability_tests', {}).get('mtr', {}).get('result', {}).get('tests', [])
    if mtr_tests:
        table_rows += 1  # Overall summary
        table_rows += len(mtr_tests)  # Individual router results
    
    # Count service test rows
    packet_analyses = results_data.get('packet_count_analysis', [])
    if packet_analyses:
        table_rows += 1  # Overall summary
        for analysis in packet_analyses:
            table_rows += 2  # Router header + mode
            # Account for wrapped text using the same wrapping function
            description = analysis.get('result', {}).get('description', '')
            desc_lines = len(wrap_text(description, width=85)) if description else 1
            table_rows += max(0, desc_lines - 1)  # Extra lines for wrapped description
            
            details = analysis.get('result', {}).get('details', '')
            if details:
                detail_lines = len(wrap_text(details, width=85))
                table_rows += detail_lines
                
            if analysis.get('blocking_rules') or analysis.get('allowing_rules'):
                table_rows += 1  # Rule row
                # Account for wrapped rule text
                rules = analysis.get('blocking_rules', []) or analysis.get('allowing_rules', [])
                if rules:
                    rule_text = rules[0].get('rule_text', '')
                    rule_lines = len(wrap_text(rule_text, width=85)) if rule_text else 1
                    table_rows += max(0, rule_lines - 1)
    
    # Each table row needs about 40 units of space
    table_space_needed = table_rows * 40 + 100  # Extra padding
    
    # Total vertical space needed
    total_height = graph_height + top_margin + table_space_needed + 200  # Extra bottom margin
    
    ax.set_xlim(min(x_coords) - x_margin, max(x_coords) + x_margin)
    ax.set_ylim(graph_lowest_y - table_space_needed - 200, 
                graph_highest_y + top_margin)
    
    # Calculate table column widths first
    col_widths = [0.15, 0.28, 0.08, 0.49]  # Narrower Router/Details, wider Analysis
    fig_width_inches = 8.27  # A4 width
    table_width_fraction = 0.9  # Table occupies 90% of figure width
    table_width_inches = fig_width_inches * table_width_fraction
    analysis_col_width_inches = table_width_inches * col_widths[3]
    
    # Convert to points and calculate usable width
    analysis_col_width_points = analysis_col_width_inches * 72
    cell_padding_points = 0.03 * 72 * 2  # Left and right padding
    usable_width_points = analysis_col_width_points - cell_padding_points - 10  # Safety margin
    
    # Calculate character width for wrapping
    # For 8pt font, average character width is about 4.3 points
    char_width_points = 4.3
    wrap_width_chars = int(usable_width_points / char_width_points)
    
    # Create table data
    table_data = []
    table_colors = []
    # Track actual wrapped content for proper height calculation
    wrapped_content = []  # Store actual wrapped lines for each row
    
    # Add header row
    table_data.append(['Test Type', 'Router/Details', 'Result', 'Analysis'])
    table_colors.append(['darkgray'] * 4)
    wrapped_content.append(1)  # Header is single line
    
    # Add Ping test results - show each router's result
    ping_tests = results_data.get('reachability_tests', {}).get('ping', {}).get('result', {}).get('tests', [])
    if ping_tests:
        ping_summary = results_data.get('reachability_tests', {}).get('ping', {}).get('result', {}).get('summary', {})
        # Overall ping summary
        table_data.append(['PING TEST', 
                          f"Overall: {ping_summary.get('passed', 0)}/{ping_summary.get('total_tests', 0)} passed", 
                          'PASS' if ping_summary.get('all_passed', False) else 'FAIL',
                          ''])  # Empty Analysis for PING
        table_colors.append(['lightgray'] * 4)
        wrapped_content.append(1)  # Single line
        
        # Individual router ping results
        for test in ping_tests:
            router = test.get('router', 'Unknown')
            table_data.append(['', 
                              f"  → {router}", 
                              'PASS' if test.get('success', False) else 'FAIL',
                              ''])  # Empty Analysis
            table_colors.append(['white'] * 4)
            wrapped_content.append(1)  # Single line
    
    # Add MTR test results - show each router's result  
    mtr_tests = results_data.get('reachability_tests', {}).get('mtr', {}).get('result', {}).get('tests', [])
    if mtr_tests:
        mtr_summary = results_data.get('reachability_tests', {}).get('mtr', {}).get('result', {}).get('summary', {})
        # Overall MTR summary
        table_data.append(['MTR TEST', 
                          f"Overall: {mtr_summary.get('passed', 0)}/{mtr_summary.get('total_tests', 0)} passed", 
                          'PASS' if mtr_summary.get('all_passed', False) else 'FAIL',
                          ''])  # Empty Analysis for MTR
        table_colors.append(['lightgray'] * 4)
        wrapped_content.append(1)  # Single line
        
        # Individual router MTR results
        for test in mtr_tests:
            router = test.get('router', 'Unknown')
            table_data.append(['', 
                              f"  → {router}", 
                              'PASS' if test.get('success', False) else 'FAIL',
                              ''])  # Empty Analysis
            table_colors.append(['white'] * 4)
            wrapped_content.append(1)  # Single line
    
    # Add Service test results with packet analysis for each router
    service_tests = results_data.get('reachability_tests', {}).get('service', {}).get('result', {}).get('tests', [])
    packet_analyses = results_data.get('packet_count_analysis', [])
    
    if service_tests or packet_analyses:
        # Overall service test summary
        service_summary = results_data.get('reachability_tests', {}).get('service', {}).get('result', {}).get('summary', {})
        table_data.append(['SERVICE TEST', 
                          f"Overall: {service_summary.get('successful', 0)}/{service_summary.get('total_tests', 0)} successful", 
                          service_summary.get('overall_status', 'N/A'),
                          f"TCP port {summary.get('destination_port', 'N/A')} connectivity"])
        table_colors.append(['lightgray'] * 4)
        wrapped_content.append(1)  # Single line
        
        # Create a mapping of router to service test results
        router_service_map = {}
        for test in service_tests:
            router = test.get('via_router', 'Unknown')
            router_service_map[router] = test
        
        # Add packet analysis for each router
        for analysis in packet_analyses:
            router_name = analysis.get('router', 'Unknown')
            mode = analysis.get('mode', 'unknown')
            result = analysis.get('result', {})
            status = result.get('status', 'unknown')
            description = result.get('description', '')
            details = result.get('details', '')
            
            # Get service test details for this router
            service_test = router_service_map.get(router_name, {})
            service_status = service_test.get('status', 'N/A')
            
            # Router header with service result
            table_data.append(['', 
                              f"  → {router_name}", 
                              service_status,
                              f"Firewall: {'ALLOWED' if status == 'allowed' else 'BLOCKED'}"])
            color = 'lightgreen' if status == 'allowed' else 'lightcoral'
            table_colors.append([color, color, color, color])
            wrapped_content.append(1)  # Single line
            
            # Add packet analysis details
            desc_lines = wrap_text(description, width=wrap_width_chars)
            table_data.append(['', 
                              f"     Mode: {mode}", 
                              '',
                              '\n'.join(desc_lines)])
            table_colors.append(['white'] * 4)
            wrapped_content.append(len(desc_lines))  # Actual line count
            
            # Add details if available
            if details:
                detail_lines = wrap_text(details, width=wrap_width_chars)
                table_data.append(['', 
                                  f"     Details", 
                                  '',
                                  '\n'.join(detail_lines)])
                table_colors.append(['white'] * 4)
                wrapped_content.append(len(detail_lines))  # Actual line count
            
            # Add relevant rules
            if status == 'blocked' and analysis.get('blocking_rules'):
                for rule in analysis['blocking_rules'][:1]:  # Show first blocking rule
                    rule_text = rule.get('rule_text', 'N/A')
                    rule_lines = wrap_text(rule_text, width=wrap_width_chars)
                    table_data.append(['', 
                                     f"     Rule #{rule.get('rule_number', 'N/A')}", 
                                     'BLOCK',
                                     '\n'.join(rule_lines)])
                    table_colors.append(['white'] * 4)
                    wrapped_content.append(len(rule_lines))  # Actual line count
            elif status == 'allowed' and analysis.get('allowing_rules'):
                for rule in analysis['allowing_rules'][:1]:  # Show first allowing rule
                    rule_text = rule.get('rule_text', 'N/A')
                    rule_lines = wrap_text(rule_text, width=wrap_width_chars)
                    table_data.append(['', 
                                     f"     Rule #{rule.get('rule_number', 'N/A')}", 
                                     'ACCEPT',
                                     '\n'.join(rule_lines)])
                    table_colors.append(['white'] * 4)
                    wrapped_content.append(len(rule_lines))  # Actual line count
    
    # Create the table
    if table_data:
        # Calculate vertical spacing
        # The spacing between description (at 0.94) and graph should equal
        # the spacing between graph and table
        # Since we use 250 units for top_margin, this translates to about 0.08-0.09 in figure coordinates
        
        # Calculate table height based on number of rows
        table_height = len(table_data) * 0.020 + 0.02  # Increased height per row for wrapped text
        
        # Move table up by reducing the y position
        # Further reduced spacing for tighter layout
        table_y_position = 0.46 - table_height  # Moved up even more for tighter spacing
        
        # Create table using matplotlib table
        table_ax = fig.add_axes([0.05, table_y_position, table_width_fraction, table_height])
        table_ax.axis('off')
        
        # Create the table
        the_table = table_ax.table(cellText=table_data,
                                  cellColours=table_colors,
                                  cellLoc='left',
                                  loc='center',
                                  colWidths=col_widths)
        
        the_table.auto_set_font_size(False)
        the_table.set_fontsize(8)
        the_table.scale(1, 1.3)  # Balanced base row height
        
        # Calculate which rows need extra height based on wrapped content
        row_heights = {}
        for i in range(len(table_data)):
            if i < len(wrapped_content):
                line_count = wrapped_content[i]
                if line_count > 1:
                    # Each additional line needs about 0.9 of the base height
                    # This ensures text fits properly
                    row_heights[i] = 1.0 + (line_count - 1) * 0.9
                else:
                    row_heights[i] = 1.0
            else:
                row_heights[i] = 1.0
        
        # Style the table
        for (i, j), cell in the_table.get_celld().items():
            if i == 0:  # Header row
                cell.set_linewidth(0.5)
                cell.set_edgecolor('gray')
                cell.set_text_props(weight='bold')
                cell.set_facecolor('darkgray')
                cell.set_text_props(color='white')
            else:
                # Test Type column (j=0) special handling
                if j == 0:
                    if table_data[i][0]:  # Cell has text
                        cell.set_linewidth(0.5)
                        cell.set_edgecolor('gray')
                        if not table_data[i][0].startswith('  '):  # Main rows
                            cell.set_text_props(weight='bold')
                        # Keep the background color from table_colors
                    else:  # Empty Test Type cell
                        # Still show outer borders but make them lighter
                        cell.set_linewidth(0.5)
                        cell.set_edgecolor('lightgray')
                        # Override background to white for empty cells
                        cell.set_facecolor('white')
                else:  # Other columns
                    cell.set_linewidth(0.5)
                    cell.set_edgecolor('gray')
            
            # Center align Result column (j=2)
            if j == 2:
                cell.set_text_props(ha='center')
            
            # Enable text wrapping for Analysis column (j=3)
            if j == 3:
                cell.set_text_props(wrap=True)
            
            # Apply variable row height
            if i in row_heights and row_heights[i] > 1.0:
                cell.set_height(cell.get_height() * row_heights[i])
                
            # Adjust text padding
            cell.PAD = 0.03
    
    # Remove axes
    ax.axis('off')
    
    # Don't use tight_layout as it causes issues
    # plt.tight_layout()
    
    # Save or show
    if output_file:
        # Save with A4 portrait dimensions
        plt.savefig(output_file, 
                    dpi=300, 
                    bbox_inches=None,  # Don't use tight - it changes the page size
                    facecolor='white',
                    format='pdf')
        print(f"Visualization saved to: {output_file}")
    else:
        plt.show()
    
    plt.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description='Visualize network reachability test results using NetworkX')
    parser.add_argument('-t', '--trace-file', required=True,
                        help='Trace file containing network path')
    parser.add_argument('-r', '--results-file', required=True,
                        help='Results file containing test results')
    parser.add_argument('-o', '--output', type=str,
                        help='Output image file (PNG, PDF, etc.)')
    
    args = parser.parse_args()
    
    try:
        # Load trace and results
        trace_data = load_json_file(args.trace_file)
        results_data = load_json_file(args.results_file)
        
        # Create visualization
        create_networkx_visualization(trace_data, results_data, args.output)
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: File not found: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing required field in JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
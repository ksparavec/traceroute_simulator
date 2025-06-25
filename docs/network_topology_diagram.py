"""
Network Topology Diagram Generator

Creates a visual representation of the 10-router network topology
using matplotlib for clear visualization of connections and interfaces.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np
import json
import os

def create_network_diagram():
    """Create a comprehensive network topology diagram with no crossing connections."""
    
    fig, ax = plt.subplots(1, 1, figsize=(22, 16))
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 16)
    ax.axis('off')
    
    # Color scheme
    colors = {
        'linux': '#90EE90',      # Light green for Linux routers
        'non_linux': '#FFB6C1',  # Light red for non-Linux routers
        'location_bg': '#FFFFE0', # Light yellow for location headers
        'text': '#2D3436'        # Dark gray for text
    }
    
    # Load router data from tsim_facts
    def load_router_data():
        facts_dir = "../tests/tsim_facts"
        routers = {}
        
        for facts_file in os.listdir(facts_dir):
            if facts_file.endswith('.json') and '_metadata' not in facts_file:
                router_name = facts_file.replace('.json', '')
                with open(os.path.join(facts_dir, facts_file), 'r') as f:
                    routers[router_name] = json.load(f)
        
        return routers
    
    # Load router metadata to determine Linux vs non-Linux
    def is_linux_router(router_name):
        metadata_path = f"../tests/tsim_facts/{router_name}_metadata.json"
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    return metadata.get('linux', True)
            except:
                pass
        return True  # Default to Linux if metadata not found
    
    # Extract interface information from router facts
    def get_router_interfaces(router_data):
        interfaces = []
        routing_data = router_data.get('routing', {})
        routes = routing_data.get('tables', [])
        
        # Extract unique interface:IP combinations
        interface_ips = {}
        for route in routes:
            if 'prefsrc' in route and 'dev' in route:
                interface = route['dev']
                ip_addr = route['prefsrc']
                if ip_addr.startswith('127.'):
                    continue
                interface_ips[interface] = ip_addr
        
        # Format as interface: IP
        for interface, ip in sorted(interface_ips.items()):
            interfaces.append(f"{interface}: {ip}")
        
        return interfaces
    
    # Load all router data
    router_data = load_router_data()
    
    # Title - moved higher to create more space
    ax.text(11, 15, 'Network Topology - 10 Routers Across 3 Locations', 
            fontsize=33, fontweight='bold', ha='center')
    
    # Location headers - positioned above each column with more space from title
    ax.text(4, 13, 'Location A (HQ)\n10.1.0.0/16', 
            fontsize=24, fontweight='bold', ha='center', 
            bbox=dict(boxstyle="round,pad=0.6", facecolor=colors['location_bg'], alpha=0.8))
    
    ax.text(11, 13, 'Location B (Branch)\n10.2.0.0/16', 
            fontsize=24, fontweight='bold', ha='center',
            bbox=dict(boxstyle="round,pad=0.6", facecolor=colors['location_bg'], alpha=0.8))
    
    ax.text(18, 13, 'Location C (DC)\n10.3.0.0/16', 
            fontsize=24, fontweight='bold', ha='center',
            bbox=dict(boxstyle="round,pad=0.6", facecolor=colors['location_bg'], alpha=0.8))
    
    
    # Gateway routers - positioned closer to location headers
    gateways = [
        {'name': 'hq-gw', 'pos': (4, 11.5), 'interfaces': get_router_interfaces(router_data['hq-gw'])},
        {'name': 'br-gw', 'pos': (11, 11.5), 'interfaces': get_router_interfaces(router_data['br-gw'])},
        {'name': 'dc-gw', 'pos': (18, 11.5), 'interfaces': get_router_interfaces(router_data['dc-gw'])}
    ]
    
    # Core routers - positioned proportionally
    cores = [
        {'name': 'hq-core', 'pos': (4, 9), 'interfaces': get_router_interfaces(router_data['hq-core'])},
        {'name': 'br-core', 'pos': (11, 9), 'interfaces': get_router_interfaces(router_data['br-core'])},
        {'name': 'dc-core', 'pos': (18, 9), 'interfaces': get_router_interfaces(router_data['dc-core'])}
    ]
    
    # Access routers - positioned proportionally
    access = [
        {'name': 'hq-dmz', 'pos': (1.8, 6.5), 'interfaces': get_router_interfaces(router_data['hq-dmz'])},
        {'name': 'hq-lab', 'pos': (6.2, 6.5), 'interfaces': get_router_interfaces(router_data['hq-lab'])},
        {'name': 'br-wifi', 'pos': (11, 6.5), 'interfaces': get_router_interfaces(router_data['br-wifi'])},
        {'name': 'dc-srv', 'pos': (18, 6.5), 'interfaces': get_router_interfaces(router_data['dc-srv'])}
    ]
    
    # Draw routers with minimal size based on content
    def draw_router(router_info):
        x, y = router_info['pos']
        router_name = router_info['name']
        
        # Determine color based on Linux status
        if is_linux_router(router_name):
            color = colors['linux']
        else:
            color = colors['non_linux']
        
        # Calculate size based on content - minimal padding
        num_interfaces = len(router_info['interfaces'])
        if num_interfaces <= 2:
            size = (2.8, 1.4)  # Compact for 2 interfaces
        elif num_interfaces == 3:
            size = (2.8, 1.8)  # Medium for 3 interfaces
        else:
            size = (2.8, 2.2)  # Larger for 4 interfaces
        
        # Router box - sized to fit content with minimal padding
        router_box = FancyBboxPatch((x-size[0]/2, y-size[1]/2), size[0], size[1],
                                   boxstyle="round,pad=0.1", 
                                   facecolor=color, 
                                   edgecolor='black', linewidth=2)
        ax.add_patch(router_box)
        
        # Router name - readable font size
        ax.text(x, y+0.4, router_info['name'], fontsize=20, fontweight='bold', 
                ha='center', color=colors['text'])
        
        # Interfaces - decreased font size by 10%
        interface_text = '\n'.join(router_info['interfaces'])
        ax.text(x, y-0.2, interface_text, fontsize=19, ha='center', 
                color=colors['text'], va='center')
    
    # Draw all routers
    for gateway in gateways:
        draw_router(gateway)
    
    for core in cores:
        draw_router(core)
        
    for acc in access:
        draw_router(acc)
    
    # Draw connections with NO crossings - all connections are perfectly vertical or horizontal
    
    # Gateway to core connections - perfectly vertical lines (adjust for smaller boxes)
    for gateway, core in zip(gateways, cores):
        gw_x = gateway['pos'][0]
        gw_bottom = gateway['pos'][1] - 0.7   # Adjust for smaller box
        core_top = core['pos'][1] + 0.7       # Adjust for smaller box
        ax.plot([gw_x, gw_x], [gw_bottom, core_top], '-', color='blue', linewidth=4)
    
    # Core to access connections - use horizontal distribution level to avoid crossings
    distribution_level = 7.8  # Level for horizontal distribution (adjusted up)
    
    # HQ distribution: hq-core to both hq-dmz and hq-lab
    hq_core_x = 4
    hq_core_bottom = 9 - 0.7   # Adjust for new position and smaller box
    hq_dmz_x = 1.8  # Use actual position from access router
    hq_lab_x = 6.2  # Use actual position from access router
    
    # Vertical drop from hq-core to distribution level
    ax.plot([hq_core_x, hq_core_x], [hq_core_bottom, distribution_level], '-', color='purple', linewidth=4)
    # Horizontal line to both access routers
    ax.plot([hq_dmz_x, hq_lab_x], [distribution_level, distribution_level], '-', color='purple', linewidth=4)
    # Vertical connections to access routers
    hq_dmz_top = 6.5 + 0.7  # hq-dmz has 2 interfaces (adjusted position)
    hq_lab_top = 6.5 + 0.9  # hq-lab has 3 interfaces (adjusted position)
    ax.plot([hq_dmz_x, hq_dmz_x], [distribution_level, hq_dmz_top], '-', color='purple', linewidth=4)
    ax.plot([hq_lab_x, hq_lab_x], [distribution_level, hq_lab_top], '-', color='purple', linewidth=4)
    
    # Branch: br-core to br-wifi - straight vertical line
    br_core_x = 11
    br_core_bottom = 9 - 0.7   # Adjust for new position and smaller box
    br_wifi_top = 6.5 + 0.9    # Adjust for new position and smaller box (3 interfaces)
    ax.plot([br_core_x, br_core_x], [br_core_bottom, br_wifi_top], '-', color='purple', linewidth=4)
    
    # DC: dc-core to dc-srv - straight vertical line
    dc_core_x = 18
    dc_core_bottom = 9 - 0.7   # Adjust for new position and smaller box
    dc_srv_top = 6.5 + 1.1     # Adjust for new position and smaller box (4 interfaces)
    ax.plot([dc_core_x, dc_core_x], [dc_core_bottom, dc_srv_top], '-', color='purple', linewidth=4)
    
    # VPN connections between gateway routers
    # hq-gw to br-gw - direct line
    ax.plot([5.4, 9.6], [11.5, 11.5], '--', color='gray', linewidth=3, alpha=0.8)
    
    # br-gw to dc-gw - direct line  
    ax.plot([12.4, 16.6], [11.5, 11.5], '--', color='gray', linewidth=3, alpha=0.8)
    
    # hq-gw to dc-gw - rectangular path going around location boxes
    # Start from left side of hq-gw box, go around Location A and Location C boxes
    hq_left_x = 1.5    # Further left to clear Location A box completely
    dc_right_x = 20.5  # Further right to clear Location C box completely
    top_y = 14.2       # Above location boxes but below title
    
    # Path: left -> up -> right -> down -> left
    # 1. Connect from hq-gw box to left starting point, then go up to clear Location A box
    ax.plot([2.6, hq_left_x], [11.5, 11.5], '--', color='gray', linewidth=3, alpha=0.8)  # Connect to hq-gw box
    ax.plot([hq_left_x, hq_left_x], [11.5, top_y], '--', color='gray', linewidth=3, alpha=0.8)
    # 2. Go right across the top, past Location C box
    ax.plot([hq_left_x, dc_right_x], [top_y, top_y], '--', color='gray', linewidth=3, alpha=0.8)
    # 3. Go down to dc-gw level
    ax.plot([dc_right_x, dc_right_x], [top_y, 11.5], '--', color='gray', linewidth=3, alpha=0.8)
    # 4. Go left to connect to dc-gw box edge (not entering the box)
    ax.plot([dc_right_x, 19.4], [11.5, 11.5], '--', color='gray', linewidth=3, alpha=0.8)
    
    # Legend
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors['linux'], 
                   markersize=15, label='Linux Routers'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors['non_linux'], 
                   markersize=15, label='Non-Linux Routers'),
        plt.Line2D([0], [0], color='blue', linewidth=4, label='Gateway-Core Connection'),
        plt.Line2D([0], [0], color='purple', linewidth=4, label='Core-Access Connection'),
        plt.Line2D([0], [0], color='gray', linewidth=3, linestyle='--', label='VPN Connections')
    ]
    
    ax.legend(handles=legend_elements, loc='lower center', bbox_to_anchor=(0.5, 0.02), 
              ncol=2, fontsize=21)
    
    plt.tight_layout()
    return fig

if __name__ == "__main__":
    # Create and save the diagram
    fig = create_network_diagram()
    
    # Save as high-resolution PNG
    plt.savefig('network_topology.png', dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    
    # Save as PDF for vector graphics
    plt.savefig('network_topology.pdf', bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    
    # plt.show()  # Commented out for headless execution
    
    print("Network topology diagram saved as:")
    print("- network_topology.png (high-resolution)")
    print("- network_topology.pdf (vector format)")
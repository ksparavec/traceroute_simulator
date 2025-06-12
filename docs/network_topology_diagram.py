"""
Network Topology Diagram Generator

Creates a visual representation of the 10-router network topology
using matplotlib for clear visualization of connections and interfaces.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch
import numpy as np

def create_network_diagram():
    """Create a comprehensive network topology diagram with no crossing connections."""
    
    fig, ax = plt.subplots(1, 1, figsize=(22, 16))
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 16)
    ax.axis('off')
    
    # Color scheme
    colors = {
        'gateway': '#FF6B6B',    # Red for gateway routers
        'core': '#4ECDC4',       # Teal for core routers  
        'access': '#45B7D1',     # Blue for access routers
        'internet': '#96CEB4',   # Green for internet
        'text': '#2D3436'        # Dark gray for text
    }
    
    # Title - moved higher to create more space
    ax.text(11, 15, 'Network Topology - 10 Routers Across 3 Locations', 
            fontsize=33, fontweight='bold', ha='center')
    
    # Location headers - positioned above each column with more space from title
    ax.text(4, 13, 'Location A (HQ)\n10.1.0.0/16', 
            fontsize=24, fontweight='bold', ha='center', 
            bbox=dict(boxstyle="round,pad=0.6", facecolor='lightblue', alpha=0.8))
    
    ax.text(11, 13, 'Location B (Branch)\n10.2.0.0/16', 
            fontsize=24, fontweight='bold', ha='center',
            bbox=dict(boxstyle="round,pad=0.6", facecolor='lightgreen', alpha=0.8))
    
    ax.text(18, 13, 'Location C (DC)\n10.3.0.0/16', 
            fontsize=24, fontweight='bold', ha='center',
            bbox=dict(boxstyle="round,pad=0.6", facecolor='lightcoral', alpha=0.8))
    
    
    # Gateway routers - positioned closer to location headers
    gateways = [
        {'name': 'hq-gw', 'pos': (4, 11.5), 'interfaces': ['eth0: 203.0.113.10', 'eth1: 10.1.1.1']},
        {'name': 'br-gw', 'pos': (11, 11.5), 'interfaces': ['eth0: 198.51.100.10', 'eth1: 10.2.1.1']},
        {'name': 'dc-gw', 'pos': (18, 11.5), 'interfaces': ['eth0: 192.0.2.10', 'eth1: 10.3.1.1']}
    ]
    
    # Core routers - positioned proportionally
    cores = [
        {'name': 'hq-core', 'pos': (4, 9), 'interfaces': ['eth0: 10.1.1.2', 'eth1: 10.1.2.1']},
        {'name': 'br-core', 'pos': (11, 9), 'interfaces': ['eth0: 10.2.1.2', 'eth1: 10.2.2.1']},
        {'name': 'dc-core', 'pos': (18, 9), 'interfaces': ['eth0: 10.3.1.2', 'eth1: 10.3.2.1']}
    ]
    
    # Access routers - positioned proportionally
    access = [
        {'name': 'hq-dmz', 'pos': (1.8, 6.5), 'interfaces': ['eth0: 10.1.2.3', 'eth1: 10.1.3.1']},
        {'name': 'hq-lab', 'pos': (6.2, 6.5), 'interfaces': ['eth0: 10.1.2.4', 'eth1: 10.1.10.1', 'eth2: 10.1.11.1']},
        {'name': 'br-wifi', 'pos': (11, 6.5), 'interfaces': ['eth0: 10.2.2.3', 'wlan0: 10.2.5.1', 'wlan1: 10.2.6.1']},
        {'name': 'dc-srv', 'pos': (18, 6.5), 'interfaces': ['eth0: 10.3.2.3', 'eth1: 10.3.10.1', 'eth2: 10.3.20.1', 'eth3: 10.3.21.1']}
    ]
    
    # Draw routers with minimal size based on content
    def draw_router(router_info, color):
        x, y = router_info['pos']
        
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
        draw_router(gateway, colors['gateway'])
    
    for core in cores:
        draw_router(core, colors['core'])
        
    for acc in access:
        draw_router(acc, colors['access'])
    
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
    
    # Legend
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors['gateway'], 
                   markersize=15, label='Gateway Routers'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors['core'], 
                   markersize=15, label='Core Routers'),
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors['access'], 
                   markersize=15, label='Access Routers'),
        plt.Line2D([0], [0], color='blue', linewidth=4, label='Gateway-Core Connection'),
        plt.Line2D([0], [0], color='purple', linewidth=4, label='Core-Access Connection')
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
    
    plt.show()
    
    print("Network topology diagram saved as:")
    print("- network_topology.png (high-resolution)")
    print("- network_topology.pdf (vector format)")
#!/usr/bin/env -S python3 -B -u
"""
Generate tsimsh CLI architecture diagram
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.lines as mlines

# Create figure
fig, ax = plt.subplots(figsize=(14, 10))
ax.set_xlim(0, 14)
ax.set_ylim(0, 10)
ax.axis('off')

# Define colors
color_cli = '#4A90E2'       # Blue for CLI layer
color_shell = '#7B68EE'     # Purple for shell layer
color_cmd = '#50C878'       # Green for commands
color_core = '#FF6B6B'      # Red for core engine
color_ns = '#FFB347'        # Orange for namespaces
color_facts = '#45B7D1'     # Cyan for facts

# Title
ax.text(7, 9.5, 'tsimsh CLI Architecture', fontsize=20, fontweight='bold', ha='center')

# Layer 1: CLI Entry Point
cli_box = FancyBboxPatch((1, 8), 12, 0.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_cli, edgecolor='black', linewidth=2)
ax.add_patch(cli_box)
ax.text(7, 8.4, 'tsimsh Entry Point', fontsize=12, fontweight='bold', ha='center', color='white')

# Layer 2: Shell Core
shell_box = FancyBboxPatch((1, 6.5), 12, 1.2,
                          boxstyle="round,pad=0.05",
                          facecolor=color_shell, edgecolor='black', linewidth=2)
ax.add_patch(shell_box)
ax.text(7, 7.3, 'TracerouteSimulatorShell (cmd2)', fontsize=12, fontweight='bold', ha='center', color='white')
ax.text(7, 6.9, 'Variable Manager | Script Processor | Completers', fontsize=10, ha='center', color='white')

# Layer 3: Command Handlers
commands = [
    ('network', 2, 'Network\nManagement'),
    ('host', 4, 'Host\nConfiguration'),
    ('service', 6, 'Service\nControl'),
    ('trace', 8, 'Traceroute\nExecution'),
    ('facts', 10, 'Facts\nCollection'),
    ('nettest', 12, 'Network\nTesting')
]

for cmd, x, label in commands:
    cmd_box = FancyBboxPatch((x-0.8, 4.8), 1.6, 1.2,
                            boxstyle="round,pad=0.05",
                            facecolor=color_cmd, edgecolor='black', linewidth=1)
    ax.add_patch(cmd_box)
    ax.text(x, 5.4, label, fontsize=9, ha='center', va='center', fontweight='bold')
    # Arrow from shell to command
    arrow = FancyArrowPatch((7, 6.5), (x, 6.0),
                          arrowstyle='->', mutation_scale=15,
                          color='gray', linewidth=1, alpha=0.6)
    ax.add_patch(arrow)

# Layer 4: Core Components
# Core Simulation Engine
core_box = FancyBboxPatch((1, 2.5), 5, 1.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(core_box)
ax.text(3.5, 3.7, 'Core Simulation Engine', fontsize=11, fontweight='bold', ha='center')
ax.text(3.5, 3.3, '• TracerouteSimulator', fontsize=9, ha='center')
ax.text(3.5, 3.0, '• PacketTracer', fontsize=9, ha='center')
ax.text(3.5, 2.7, '• RuleDatabase', fontsize=9, ha='center')

# Namespace Manager
ns_box = FancyBboxPatch((6.5, 2.5), 3.5, 1.8,
                       boxstyle="round,pad=0.05",
                       facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(ns_box)
ax.text(8.25, 3.7, 'Namespace Manager', fontsize=11, fontweight='bold', ha='center')
ax.text(8.25, 3.3, '• Network Setup', fontsize=9, ha='center')
ax.text(8.25, 3.0, '• Host Setup', fontsize=9, ha='center')
ax.text(8.25, 2.7, '• Service Manager', fontsize=9, ha='center')

# Ansible Facts Integration
facts_box = FancyBboxPatch((10.5, 2.5), 2.5, 1.8,
                          boxstyle="round,pad=0.05",
                          facecolor=color_facts, edgecolor='black', linewidth=2)
ax.add_patch(facts_box)
ax.text(11.75, 3.7, 'Ansible Facts', fontsize=11, fontweight='bold', ha='center')
ax.text(11.75, 3.3, '• Playbook', fontsize=9, ha='center')
ax.text(11.75, 3.0, '• Collector', fontsize=9, ha='center')
ax.text(11.75, 2.7, '• Processor', fontsize=9, ha='center')

# Layer 5: Data Layer
data_box = FancyBboxPatch((1, 0.5), 12, 1.2,
                         boxstyle="round,pad=0.05",
                         facecolor='#E8E8E8', edgecolor='black', linewidth=2)
ax.add_patch(data_box)
ax.text(7, 1.3, 'Data Layer', fontsize=11, fontweight='bold', ha='center')
ax.text(4, 0.9, 'Raw Facts Files', fontsize=9, ha='center')
ax.text(7, 0.9, 'Configuration Files', fontsize=9, ha='center')
ax.text(10, 0.9, 'Network Namespaces', fontsize=9, ha='center')

# Arrows from commands to core components
# Network/Host/Service -> Namespace Manager
for x in [2, 4, 6]:
    arrow = FancyArrowPatch((x, 4.8), (8.25, 4.3),
                          arrowstyle='->', mutation_scale=12,
                          color='darkgray', linewidth=1.5)
    ax.add_patch(arrow)

# Trace -> Core Engine
arrow = FancyArrowPatch((8, 4.8), (3.5, 4.3),
                      arrowstyle='->', mutation_scale=12,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Facts -> Ansible Facts
arrow = FancyArrowPatch((10, 4.8), (11.75, 4.3),
                      arrowstyle='->', mutation_scale=12,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Core components to data layer
for x in [3.5, 8.25, 11.75]:
    arrow = FancyArrowPatch((x, 2.5), (x, 1.7),
                          arrowstyle='<->', mutation_scale=12,
                          color='darkgray', linewidth=1.5)
    ax.add_patch(arrow)

# Add legend
legend_elements = [
    mpatches.Patch(color=color_cli, label='CLI Layer'),
    mpatches.Patch(color=color_shell, label='Shell Framework'),
    mpatches.Patch(color=color_cmd, label='Command Handlers'),
    mpatches.Patch(color=color_core, label='Core Engine'),
    mpatches.Patch(color=color_ns, label='Namespace Manager'),
    mpatches.Patch(color=color_facts, label='Ansible Integration')
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=9)

# Add execution flow annotation
ax.text(0.5, 9, 'Execution Flow:', fontsize=10, fontweight='bold')
ax.text(0.5, 8.6, '1. User input via tsimsh', fontsize=8)
ax.text(0.5, 8.3, '2. cmd2 parses command', fontsize=8)
ax.text(0.5, 8.0, '3. Handler processes request', fontsize=8)
ax.text(0.5, 7.7, '4. Core components execute', fontsize=8)
ax.text(0.5, 7.4, '5. Data layer accessed', fontsize=8)

plt.tight_layout()
plt.savefig('tsimsh_architecture.png', dpi=300, bbox_inches='tight', facecolor='white')
plt.show()

print("tsimsh architecture diagram saved as tsimsh_architecture.png")
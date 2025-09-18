#!/usr/bin/env -S python3 -B -u
"""
Generate overall system architecture diagram
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import matplotlib.lines as mlines

# Create figure
fig, ax = plt.subplots(figsize=(16, 10))
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis('off')

# Define colors
color_user = '#2ECC71'      # Green for user interfaces
color_cli = '#4A90E2'        # Blue for CLI
color_web = '#FF6B6B'        # Red for web
color_core = '#9B59B6'      # Purple for core
color_ns = '#E67E22'        # Orange for namespace
color_data = '#34495E'      # Dark gray for data
color_ansible = '#16A085'   # Teal for Ansible

# Title
ax.text(8, 9.5, 'Traceroute Simulator - Overall System Architecture', fontsize=20, fontweight='bold', ha='center')

# User Interfaces Section
user_box = FancyBboxPatch((0.5, 7), 7, 1.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_user, edgecolor='black', linewidth=2, alpha=0.3)
ax.add_patch(user_box)
ax.text(4, 8.5, 'User Interfaces', fontsize=12, fontweight='bold', ha='center')

# tsimsh CLI
cli_box = FancyBboxPatch((1, 7.3), 2.8, 1.2,
                        boxstyle="round,pad=0.05",
                        facecolor=color_cli, edgecolor='black', linewidth=2)
ax.add_patch(cli_box)
ax.text(2.4, 8.1, 'tsimsh CLI', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(2.4, 7.7, 'Interactive Shell', fontsize=9, ha='center', color='white')
ax.text(2.4, 7.5, 'Batch Processing', fontsize=9, ha='center', color='white')

# WSGI Web
web_box = FancyBboxPatch((4.2, 7.3), 2.8, 1.2,
                        boxstyle="round,pad=0.05",
                        facecolor=color_web, edgecolor='black', linewidth=2)
ax.add_patch(web_box)
ax.text(5.6, 8.1, 'WSGI Web', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(5.6, 7.7, 'Apache/mod_wsgi', fontsize=9, ha='center', color='white')
ax.text(5.6, 7.5, 'Web Interface', fontsize=9, ha='center', color='white')

# External Tools Section
external_box = FancyBboxPatch((8.5, 7), 7, 1.8,
                             boxstyle="round,pad=0.05",
                             facecolor=color_ansible, edgecolor='black', linewidth=2, alpha=0.3)
ax.add_patch(external_box)
ax.text(12, 8.5, 'External Integration', fontsize=12, fontweight='bold', ha='center')

# Ansible Facts
ansible_box = FancyBboxPatch((9, 7.3), 2.8, 1.2,
                            boxstyle="round,pad=0.05",
                            facecolor=color_ansible, edgecolor='black', linewidth=2)
ax.add_patch(ansible_box)
ax.text(10.4, 8.1, 'Ansible Facts', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(10.4, 7.7, 'get_tsim_facts.yml', fontsize=9, ha='center', color='white')
ax.text(10.4, 7.5, 'Collector/Processor', fontsize=9, ha='center', color='white')

# Management Tools
mgmt_box = FancyBboxPatch((12.2, 7.3), 2.8, 1.2,
                         boxstyle="round,pad=0.05",
                         facecolor=color_ansible, edgecolor='black', linewidth=2)
ax.add_patch(mgmt_box)
ax.text(13.6, 8.1, 'System Tools', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(13.6, 7.7, 'systemctl', fontsize=9, ha='center', color='white')
ax.text(13.6, 7.5, 'Process Control', fontsize=9, ha='center', color='white')

# Core Simulation Layer
core_layer_box = FancyBboxPatch((0.5, 3.8), 15, 2.8,
                               boxstyle="round,pad=0.05",
                               facecolor=color_core, edgecolor='black', linewidth=3, alpha=0.2)
ax.add_patch(core_layer_box)
ax.text(8, 6.3, 'Core Simulation Layer', fontsize=14, fontweight='bold', ha='center')

# Core Engine
core_box = FancyBboxPatch((1.5, 4.2), 4, 1.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(core_box)
ax.text(3.5, 5.5, 'Simulation Engine', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(3.5, 5.1, '• TracerouteSimulator', fontsize=9, ha='center', color='white')
ax.text(3.5, 4.8, '• PacketTracer', fontsize=9, ha='center', color='white')
ax.text(3.5, 4.5, '• RuleDatabase', fontsize=9, ha='center', color='white')

# Command System
cmd_box = FancyBboxPatch((6, 4.2), 4, 1.8,
                        boxstyle="round,pad=0.05",
                        facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(cmd_box)
ax.text(8, 5.5, 'Command System', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(8, 5.1, '• Command Handlers', fontsize=9, ha='center', color='white')
ax.text(8, 4.8, '• Script Processor', fontsize=9, ha='center', color='white')
ax.text(8, 4.5, '• Variable Manager', fontsize=9, ha='center', color='white')

# Queue & Scheduling
queue_box = FancyBboxPatch((10.5, 4.2), 4, 1.8,
                          boxstyle="round,pad=0.05",
                          facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(queue_box)
ax.text(12.5, 5.5, 'Queue & Scheduling', fontsize=11, fontweight='bold', ha='center', color='white')
ax.text(12.5, 5.1, '• Queue Service', fontsize=9, ha='center', color='white')
ax.text(12.5, 4.8, '• Scheduler', fontsize=9, ha='center', color='white')
ax.text(12.5, 4.5, '• Lock Manager', fontsize=9, ha='center', color='white')

# Infrastructure Layer
infra_layer_box = FancyBboxPatch((0.5, 1.3), 15, 2.2,
                                boxstyle="round,pad=0.05",
                                facecolor=color_ns, edgecolor='black', linewidth=3, alpha=0.2)
ax.add_patch(infra_layer_box)
ax.text(8, 3.2, 'Infrastructure Layer', fontsize=14, fontweight='bold', ha='center')

# Namespace Manager
ns_mgr_box = FancyBboxPatch((1.5, 1.6), 4, 1.4,
                           boxstyle="round,pad=0.05",
                           facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(ns_mgr_box)
ax.text(3.5, 2.7, 'Namespace Manager', fontsize=11, fontweight='bold', ha='center')
ax.text(3.5, 2.3, '• Network Setup', fontsize=9, ha='center')
ax.text(3.5, 2.0, '• Host Configuration', fontsize=9, ha='center')
ax.text(3.5, 1.7, '• Interface Management', fontsize=9, ha='center')

# Service Manager
svc_box = FancyBboxPatch((6, 1.6), 4, 1.4,
                        boxstyle="round,pad=0.05",
                        facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(svc_box)
ax.text(8, 2.7, 'Service Manager', fontsize=11, fontweight='bold', ha='center')
ax.text(8, 2.3, '• Process Control', fontsize=9, ha='center')
ax.text(8, 2.0, '• Service Testing', fontsize=9, ha='center')
ax.text(8, 1.7, '• Port Management', fontsize=9, ha='center')

# Monitoring & Progress
monitor_box = FancyBboxPatch((10.5, 1.6), 4, 1.4,
                            boxstyle="round,pad=0.05",
                            facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(monitor_box)
ax.text(12.5, 2.7, 'Monitoring', fontsize=11, fontweight='bold', ha='center')
ax.text(12.5, 2.3, '• Progress Tracker', fontsize=9, ha='center')
ax.text(12.5, 2.0, '• Performance Metrics', fontsize=9, ha='center')
ax.text(12.5, 1.7, '• SSE Streaming', fontsize=9, ha='center')

# Data Layer
data_layer_box = FancyBboxPatch((0.5, 0.1), 15, 0.9,
                               boxstyle="round,pad=0.05",
                               facecolor=color_data, edgecolor='black', linewidth=2)
ax.add_patch(data_layer_box)
ax.text(8, 0.55, 'Data Layer', fontsize=12, fontweight='bold', ha='center', color='white')
ax.text(3, 0.3, 'Raw Facts', fontsize=9, ha='center', color='white')
ax.text(5.5, 0.3, 'Configuration', fontsize=9, ha='center', color='white')
ax.text(8, 0.3, 'Session Storage', fontsize=9, ha='center', color='white')
ax.text(10.5, 0.3, 'Queue Database', fontsize=9, ha='center', color='white')
ax.text(13, 0.3, 'Namespaces', fontsize=9, ha='center', color='white')

# Connection Arrows
# User interfaces to Core
arrow = FancyArrowPatch((2.4, 7.3), (3.5, 6.0),
                      arrowstyle='->', mutation_scale=15,
                      color='darkblue', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((5.6, 7.3), (8, 6.0),
                      arrowstyle='->', mutation_scale=15,
                      color='darkred', linewidth=2)
ax.add_patch(arrow)

# Ansible to Core
arrow = FancyArrowPatch((10.4, 7.3), (8, 6.0),
                      arrowstyle='->', mutation_scale=15,
                      color='darkcyan', linewidth=2)
ax.add_patch(arrow)

# Core to Infrastructure
arrow = FancyArrowPatch((3.5, 4.2), (3.5, 3.0),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((8, 4.2), (8, 3.0),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((12.5, 4.2), (12.5, 3.0),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

# Infrastructure to Data
arrow = FancyArrowPatch((3.5, 1.6), (3.5, 1.0),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((8, 1.6), (8, 1.0),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((12.5, 1.6), (12.5, 1.0),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)

# Add Key Features annotation
ax.text(0.2, 9, 'Key Features:', fontsize=10, fontweight='bold')
ax.text(0.2, 8.6, '• Dual interface design', fontsize=8)
ax.text(0.2, 8.3, '• Ansible integration', fontsize=8)
ax.text(0.2, 8.0, '• Queue-based execution', fontsize=8)
ax.text(0.2, 7.7, '• Network namespaces', fontsize=8)
ax.text(0.2, 7.4, '• Real-time monitoring', fontsize=8)

# Add Data Flow annotation
ax.text(15.8, 6, 'Data', fontsize=9, fontweight='bold', rotation=90, ha='center')
ax.text(15.8, 5.4, 'Flow', fontsize=9, fontweight='bold', rotation=90, ha='center')
ax.text(15.8, 4.5, '↓', fontsize=14, fontweight='bold', rotation=0, ha='center')
ax.text(15.8, 3.5, '↑', fontsize=14, fontweight='bold', rotation=0, ha='center')

plt.tight_layout()
plt.savefig('overall_architecture.png', dpi=300, bbox_inches='tight', facecolor='white')
plt.show()

print("Overall architecture diagram saved as overall_architecture.png")
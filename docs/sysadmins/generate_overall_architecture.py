#!/usr/bin/env -S python3 -B -u
"""
Generate overall system architecture diagram
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import matplotlib.lines as mlines

# Create figure
fig, ax = plt.subplots(figsize=(16, 12))
ax.set_xlim(0, 16)
ax.set_ylim(0, 12)
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
ax.text(8, 11.5, 'Traceroute Simulator - Overall System Architecture', fontsize=20, fontweight='bold', ha='center')

# User Interfaces Section
user_box = FancyBboxPatch((0.5, 9), 7, 2.2,
                         boxstyle="round,pad=0.05",
                         facecolor=color_user, edgecolor='black', linewidth=2, alpha=0.3)
ax.add_patch(user_box)
ax.text(4, 11.0, 'User Interfaces', fontsize=14, fontweight='bold', ha='center')

# tsimsh CLI
cli_box = FancyBboxPatch((1, 9.3), 2.8, 1.4,
                        boxstyle="round,pad=0.05",
                        facecolor=color_cli, edgecolor='black', linewidth=2)
ax.add_patch(cli_box)
ax.text(2.4, 10.2, 'tsimsh CLI', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(2.4, 9.8, 'Interactive Shell', fontsize=11, ha='center', color='white')
ax.text(2.4, 9.5, 'Batch Processing', fontsize=11, ha='center', color='white')

# WSGI Web
web_box = FancyBboxPatch((4.2, 9.3), 2.8, 1.4,
                        boxstyle="round,pad=0.05",
                        facecolor=color_web, edgecolor='black', linewidth=2)
ax.add_patch(web_box)
ax.text(5.6, 10.2, 'WSGI Web', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(5.6, 9.8, 'Apache/mod_wsgi', fontsize=11, ha='center', color='white')
ax.text(5.6, 9.5, 'Web Interface', fontsize=11, ha='center', color='white')

# External Tools Section
external_box = FancyBboxPatch((8.5, 9), 7, 2.2,
                             boxstyle="round,pad=0.05",
                             facecolor=color_ansible, edgecolor='black', linewidth=2, alpha=0.3)
ax.add_patch(external_box)
ax.text(12, 11.0, 'External Integration', fontsize=14, fontweight='bold', ha='center')

# Ansible Facts
ansible_box = FancyBboxPatch((9, 9.3), 2.8, 1.4,
                            boxstyle="round,pad=0.05",
                            facecolor=color_ansible, edgecolor='black', linewidth=2)
ax.add_patch(ansible_box)
ax.text(10.4, 10.2, 'Ansible Facts', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(10.4, 9.8, 'get_tsim_facts.yml', fontsize=11, ha='center', color='white')
ax.text(10.4, 9.5, 'Collector/Processor', fontsize=11, ha='center', color='white')

# Management Tools
mgmt_box = FancyBboxPatch((12.2, 9.3), 2.8, 1.4,
                         boxstyle="round,pad=0.05",
                         facecolor=color_ansible, edgecolor='black', linewidth=2)
ax.add_patch(mgmt_box)
ax.text(13.6, 10.2, 'System Tools', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(13.6, 9.8, 'systemctl', fontsize=11, ha='center', color='white')
ax.text(13.6, 9.5, 'Process Control', fontsize=11, ha='center', color='white')

# Core Simulation Layer
core_layer_box = FancyBboxPatch((0.5, 6.0), 15, 2.8,
                               boxstyle="round,pad=0.05",
                               facecolor=color_core, edgecolor='black', linewidth=3, alpha=0.2)
ax.add_patch(core_layer_box)
ax.text(8, 8.4, 'Core Simulation Layer', fontsize=16, fontweight='bold', ha='center')

# Core Engine
core_box = FancyBboxPatch((1.5, 6.4), 4, 1.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(core_box)
ax.text(3.5, 7.7, 'Simulation Engine', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(3.5, 7.3, '• TracerouteSimulator', fontsize=11, ha='center', color='white')
ax.text(3.5, 7.0, '• PacketTracer', fontsize=11, ha='center', color='white')
ax.text(3.5, 6.7, '• RuleDatabase', fontsize=11, ha='center', color='white')

# Command System
cmd_box = FancyBboxPatch((6, 6.4), 4, 1.8,
                        boxstyle="round,pad=0.05",
                        facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(cmd_box)
ax.text(8, 7.7, 'Command System', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(8, 7.3, '• Command Handlers', fontsize=11, ha='center', color='white')
ax.text(8, 7.0, '• Script Processor', fontsize=11, ha='center', color='white')
ax.text(8, 6.7, '• Variable Manager', fontsize=11, ha='center', color='white')

# Queue & Scheduling
queue_box = FancyBboxPatch((10.5, 6.4), 4, 1.8,
                          boxstyle="round,pad=0.05",
                          facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(queue_box)
ax.text(12.5, 7.7, 'Queue & Scheduling', fontsize=13, fontweight='bold', ha='center', color='white')
ax.text(12.5, 7.3, '• Queue Service', fontsize=11, ha='center', color='white')
ax.text(12.5, 7.0, '• Scheduler', fontsize=11, ha='center', color='white')
ax.text(12.5, 6.7, '• Lock Manager', fontsize=11, ha='center', color='white')

# Infrastructure Layer
infra_layer_box = FancyBboxPatch((0.5, 3.5), 15, 2.2,
                                boxstyle="round,pad=0.05",
                                facecolor=color_ns, edgecolor='black', linewidth=3, alpha=0.2)
ax.add_patch(infra_layer_box)
ax.text(8, 5.4, 'Infrastructure Layer', fontsize=16, fontweight='bold', ha='center')

# Namespace Manager
ns_mgr_box = FancyBboxPatch((1.5, 3.8), 4, 1.4,
                           boxstyle="round,pad=0.05",
                           facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(ns_mgr_box)
ax.text(3.5, 4.9, 'Namespace Manager', fontsize=13, fontweight='bold', ha='center')
ax.text(3.5, 4.5, '• Network Setup', fontsize=11, ha='center')
ax.text(3.5, 4.2, '• Host Configuration', fontsize=11, ha='center')
ax.text(3.5, 3.9, '• Interface Management', fontsize=11, ha='center')

# Service Manager
svc_box = FancyBboxPatch((6, 3.8), 4, 1.4,
                        boxstyle="round,pad=0.05",
                        facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(svc_box)
ax.text(8, 4.9, 'Service Manager', fontsize=13, fontweight='bold', ha='center')
ax.text(8, 4.5, '• Process Control', fontsize=11, ha='center')
ax.text(8, 4.2, '• Service Testing', fontsize=11, ha='center')
ax.text(8, 3.9, '• Port Management', fontsize=11, ha='center')

# Monitoring & Progress
monitor_box = FancyBboxPatch((10.5, 3.8), 4, 1.4,
                            boxstyle="round,pad=0.05",
                            facecolor=color_ns, edgecolor='black', linewidth=2)
ax.add_patch(monitor_box)
ax.text(12.5, 4.9, 'Monitoring', fontsize=13, fontweight='bold', ha='center')
ax.text(12.5, 4.5, '• Progress Tracker', fontsize=11, ha='center')
ax.text(12.5, 4.2, '• Performance Metrics', fontsize=11, ha='center')
ax.text(12.5, 3.9, '• SSE Streaming', fontsize=11, ha='center')

# Data Layer
data_layer_box = FancyBboxPatch((0.5, 2.3), 15, 0.9,
                               boxstyle="round,pad=0.05",
                               facecolor=color_data, edgecolor='black', linewidth=2)
ax.add_patch(data_layer_box)
ax.text(8, 2.75, 'Data Layer', fontsize=14, fontweight='bold', ha='center', color='white')
ax.text(3, 2.5, 'Raw Facts', fontsize=11, ha='center', color='white')
ax.text(5.5, 2.5, 'Configuration', fontsize=11, ha='center', color='white')
ax.text(8, 2.5, 'Session Storage', fontsize=11, ha='center', color='white')
ax.text(10.5, 2.5, 'Queue Database', fontsize=11, ha='center', color='white')
ax.text(13, 2.5, 'Namespaces', fontsize=11, ha='center', color='white')

# Connection Arrows
# User interfaces to Core
arrow = FancyArrowPatch((2.4, 9.3), (3.5, 8.2),
                      arrowstyle='->', mutation_scale=15,
                      color='darkblue', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((5.6, 9.3), (8, 8.2),
                      arrowstyle='->', mutation_scale=15,
                      color='darkred', linewidth=2)
ax.add_patch(arrow)

# Ansible to Core
arrow = FancyArrowPatch((10.4, 9.3), (8, 8.2),
                      arrowstyle='->', mutation_scale=15,
                      color='darkcyan', linewidth=2)
ax.add_patch(arrow)

# Core to Infrastructure
arrow = FancyArrowPatch((3.5, 6.4), (3.5, 5.2),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((8, 6.4), (8, 5.2),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

arrow = FancyArrowPatch((12.5, 6.4), (12.5, 5.2),
                      arrowstyle='<->', mutation_scale=15,
                      color='purple', linewidth=2)
ax.add_patch(arrow)

# Infrastructure to Data
arrow = FancyArrowPatch((3.5, 3.8), (3.5, 3.2),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((8, 3.8), (8, 3.2),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((12.5, 3.8), (12.5, 3.2),
                      arrowstyle='<->', mutation_scale=12,
                      color='darkorange', linewidth=1.5)
ax.add_patch(arrow)


plt.tight_layout()
plt.savefig('overall_architecture.png', dpi=300, bbox_inches='tight', facecolor='white')
plt.show()

print("Overall architecture diagram saved as overall_architecture.png")
#!/usr/bin/env -S python3 -B -u
"""
Generate WSGI web interface architecture diagram
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.lines as mlines

# Create figure
fig, ax = plt.subplots(figsize=(14, 12))
ax.set_xlim(0, 14)
ax.set_ylim(0, 12)
ax.axis('off')

# Define colors
color_web = '#FF6B6B'        # Red for web layer
color_wsgi = '#4A90E2'       # Blue for WSGI
color_handler = '#50C878'    # Green for handlers
color_service = '#7B68EE'    # Purple for services
color_core = '#FFB347'       # Orange for core
color_queue = '#45B7D1'      # Cyan for queue

# Title
ax.text(7, 11.5, 'WSGI Web Interface Architecture', fontsize=20, fontweight='bold', ha='center')

# Layer 1: Web Server
web_box = FancyBboxPatch((1, 10), 12, 0.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_web, edgecolor='black', linewidth=2)
ax.add_patch(web_box)
ax.text(7, 10.4, 'Apache/mod_wsgi', fontsize=14, fontweight='bold', ha='center', color='white')

# Layer 2: WSGI Application
wsgi_box = FancyBboxPatch((1, 8.8), 12, 0.9,
                         boxstyle="round,pad=0.05",
                         facecolor=color_wsgi, edgecolor='black', linewidth=2)
ax.add_patch(wsgi_box)
ax.text(7, 9.25, 'TsimWSGIApp (app.wsgi → tsim_app.py)', fontsize=14, fontweight='bold', ha='center', color='white')

# Layer 3: Request Handlers
handlers = [
    ('Login', 1.5, '/login'),
    ('Main', 3, '/main'),
    ('Progress', 4.5, '/progress'),
    ('PDF', 6, '/pdf'),
    ('Queue Admin', 7.5, '/admin-queue'),
    ('Job Details', 9, '/admin-job'),
    ('Cleanup', 10.5, '/cleanup'),
    ('Config', 12, '/services-config')
]

y_handler = 7.5
for name, x, path in handlers[:4]:
    handler_box = FancyBboxPatch((x-0.6, y_handler), 1.2, 1.0,
                                boxstyle="round,pad=0.02",
                                facecolor=color_handler, edgecolor='black', linewidth=1)
    ax.add_patch(handler_box)
    ax.text(x, y_handler+0.6, name, fontsize=10, ha='center', fontweight='bold')
    ax.text(x, y_handler+0.3, path, fontsize=9, ha='center', style='italic')
    # Arrow from WSGI to handler
    arrow = FancyArrowPatch((x, 8.8), (x, y_handler+1.0),
                          arrowstyle='->', mutation_scale=10,
                          color='gray', linewidth=1, alpha=0.6)
    ax.add_patch(arrow)

# Admin handlers row
y_handler = 6.2
for name, x, path in handlers[4:]:
    handler_box = FancyBboxPatch((x-0.6, y_handler), 1.2, 1.0,
                                boxstyle="round,pad=0.02",
                                facecolor=color_handler, edgecolor='black', linewidth=1)
    ax.add_patch(handler_box)
    ax.text(x, y_handler+0.6, name, fontsize=10, ha='center', fontweight='bold')
    ax.text(x, y_handler+0.3, path, fontsize=9, ha='center', style='italic')
    # Arrow from WSGI to handler
    arrow = FancyArrowPatch((x, 8.8), (x, y_handler+1.0),
                          arrowstyle='->', mutation_scale=10,
                          color='gray', linewidth=1, alpha=0.6)
    ax.add_patch(arrow)

# Layer 4: Core Services
# Session Manager
session_box = FancyBboxPatch((1, 4.6), 2.5, 1.4,
                            boxstyle="round,pad=0.05",
                            facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(session_box)
ax.text(2.25, 5.5, 'Session Manager', fontsize=12, fontweight='bold', ha='center', color='white')
ax.text(2.25, 5.1, '• Auth Service', fontsize=10, ha='center', color='white')
ax.text(2.25, 4.8, '• Cookie Handler', fontsize=10, ha='center', color='white')

# Config & Logger
config_box = FancyBboxPatch((3.8, 4.6), 2.5, 1.4,
                           boxstyle="round,pad=0.05",
                           facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(config_box)
ax.text(5.05, 5.5, 'Config Service', fontsize=12, fontweight='bold', ha='center', color='white')
ax.text(5.05, 5.1, '• Logger Service', fontsize=10, ha='center', color='white')
ax.text(5.05, 4.8, '• Validator', fontsize=10, ha='center', color='white')

# Queue System
queue_box = FancyBboxPatch((6.6, 4.6), 3.2, 1.4,
                          boxstyle="round,pad=0.05",
                          facecolor=color_queue, edgecolor='black', linewidth=2)
ax.add_patch(queue_box)
ax.text(8.2, 5.5, 'Queue System', fontsize=12, fontweight='bold', ha='center')
ax.text(8.2, 5.1, '• Queue Service', fontsize=10, ha='center')
ax.text(8.2, 4.8, '• Scheduler • Lock Manager', fontsize=10, ha='center')

# Executor System
executor_box = FancyBboxPatch((10, 4.6), 3, 1.4,
                             boxstyle="round,pad=0.05",
                             facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(executor_box)
ax.text(11.5, 5.5, 'Execution System', fontsize=12, fontweight='bold', ha='center', color='white')
ax.text(11.5, 5.1, '• Hybrid Executor', fontsize=10, ha='center', color='white')
ax.text(11.5, 4.8, '• Progress Tracker', fontsize=10, ha='center', color='white')

# Layer 5: Core Engine & Namespace Layer
core_engine_box = FancyBboxPatch((1, 3.0), 6, 1.3,
                                boxstyle="round,pad=0.05",
                                facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(core_engine_box)
ax.text(4, 3.8, 'Core Simulation Engine', fontsize=12, fontweight='bold', ha='center')
ax.text(4, 3.4, 'TracerouteSimulator • PacketTracer • RuleDatabase', fontsize=10, ha='center')

ns_box = FancyBboxPatch((7.5, 3.0), 5.5, 1.3,
                       boxstyle="round,pad=0.05",
                       facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(ns_box)
ax.text(10.25, 3.8, 'Namespace Management', fontsize=12, fontweight='bold', ha='center')
ax.text(10.25, 3.4, 'Network Setup • Service Manager • Host Configuration', fontsize=10, ha='center')

# Data Layer
data_box = FancyBboxPatch((1, 1.9), 12, 0.8,
                         boxstyle="round,pad=0.05",
                         facecolor='#E8E8E8', edgecolor='black', linewidth=2)
ax.add_patch(data_box)
ax.text(7, 2.3, 'Data Layer: Raw Facts • Configuration • Session Storage • Queue Database',
        fontsize=11, ha='center')

# Arrows connecting layers
# Handlers to Services
for x in [1.5, 3, 4.5, 6]:
    arrow = FancyArrowPatch((x, 7.5), (5, 6.0),
                          arrowstyle='->', mutation_scale=10,
                          color='darkgray', linewidth=1.2, alpha=0.7)
    ax.add_patch(arrow)

for x in [7.5, 9, 10.5, 12]:
    arrow = FancyArrowPatch((x, 6.2), (8.2, 6.0),
                          arrowstyle='->', mutation_scale=10,
                          color='darkgray', linewidth=1.2, alpha=0.7)
    ax.add_patch(arrow)

# Services to Core
arrow = FancyArrowPatch((8.2, 4.6), (7, 4.3),
                      arrowstyle='->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((11.5, 4.6), (10.25, 4.3),
                      arrowstyle='->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Core to Data
arrow = FancyArrowPatch((4, 3.0), (4, 2.7),
                      arrowstyle='<->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((10.25, 3.0), (10.25, 2.7),
                      arrowstyle='<->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Add legend below the graph
legend_elements = [
    mpatches.Patch(color=color_web, label='Web Server'),
    mpatches.Patch(color=color_wsgi, label='WSGI Application'),
    mpatches.Patch(color=color_handler, label='Request Handlers'),
    mpatches.Patch(color=color_service, label='Core Services'),
    mpatches.Patch(color=color_queue, label='Queue System'),
    mpatches.Patch(color=color_core, label='Core Engine')
]
ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, 0.12), ncol=3, fontsize=11)


plt.tight_layout()
plt.savefig('wsgi_architecture.png', dpi=300, bbox_inches='tight', facecolor='white')
plt.show()

print("WSGI architecture diagram saved as wsgi_architecture.png")
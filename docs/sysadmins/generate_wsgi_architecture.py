#!/usr/bin/env -S python3 -B -u
"""
Generate WSGI web interface architecture diagram
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
color_web = '#FF6B6B'        # Red for web layer
color_wsgi = '#4A90E2'       # Blue for WSGI
color_handler = '#50C878'    # Green for handlers
color_service = '#7B68EE'    # Purple for services
color_core = '#FFB347'       # Orange for core
color_queue = '#45B7D1'      # Cyan for queue

# Title
ax.text(7, 9.5, 'WSGI Web Interface Architecture', fontsize=20, fontweight='bold', ha='center')

# Layer 1: Web Server
web_box = FancyBboxPatch((1, 8), 12, 0.8,
                         boxstyle="round,pad=0.05",
                         facecolor=color_web, edgecolor='black', linewidth=2)
ax.add_patch(web_box)
ax.text(7, 8.4, 'Apache/mod_wsgi', fontsize=12, fontweight='bold', ha='center', color='white')

# Layer 2: WSGI Application
wsgi_box = FancyBboxPatch((1, 6.8), 12, 0.9,
                         boxstyle="round,pad=0.05",
                         facecolor=color_wsgi, edgecolor='black', linewidth=2)
ax.add_patch(wsgi_box)
ax.text(7, 7.25, 'TsimWSGIApp (app.wsgi → tsim_app.py)', fontsize=12, fontweight='bold', ha='center', color='white')

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

y_handler = 5.5
for name, x, path in handlers[:4]:
    handler_box = FancyBboxPatch((x-0.6, y_handler), 1.2, 0.8,
                                boxstyle="round,pad=0.02",
                                facecolor=color_handler, edgecolor='black', linewidth=1)
    ax.add_patch(handler_box)
    ax.text(x, y_handler+0.5, name, fontsize=8, ha='center', fontweight='bold')
    ax.text(x, y_handler+0.2, path, fontsize=7, ha='center', style='italic')
    # Arrow from WSGI to handler
    arrow = FancyArrowPatch((x, 6.8), (x, y_handler+0.8),
                          arrowstyle='->', mutation_scale=10,
                          color='gray', linewidth=1, alpha=0.6)
    ax.add_patch(arrow)

# Admin handlers row
y_handler = 4.4
for name, x, path in handlers[4:]:
    handler_box = FancyBboxPatch((x-0.6, y_handler), 1.2, 0.8,
                                boxstyle="round,pad=0.02",
                                facecolor=color_handler, edgecolor='black', linewidth=1)
    ax.add_patch(handler_box)
    ax.text(x, y_handler+0.5, name, fontsize=8, ha='center', fontweight='bold')
    ax.text(x, y_handler+0.2, path, fontsize=7, ha='center', style='italic')
    # Arrow from WSGI to handler
    arrow = FancyArrowPatch((x, 6.8), (x, y_handler+0.8),
                          arrowstyle='->', mutation_scale=10,
                          color='gray', linewidth=1, alpha=0.6)
    ax.add_patch(arrow)

# Layer 4: Core Services
# Session Manager
session_box = FancyBboxPatch((1, 2.8), 2.5, 1.2,
                            boxstyle="round,pad=0.05",
                            facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(session_box)
ax.text(2.25, 3.6, 'Session Manager', fontsize=10, fontweight='bold', ha='center', color='white')
ax.text(2.25, 3.3, '• Auth Service', fontsize=8, ha='center', color='white')
ax.text(2.25, 3.0, '• Cookie Handler', fontsize=8, ha='center', color='white')

# Config & Logger
config_box = FancyBboxPatch((3.8, 2.8), 2.5, 1.2,
                           boxstyle="round,pad=0.05",
                           facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(config_box)
ax.text(5.05, 3.6, 'Config Service', fontsize=10, fontweight='bold', ha='center', color='white')
ax.text(5.05, 3.3, '• Logger Service', fontsize=8, ha='center', color='white')
ax.text(5.05, 3.0, '• Validator', fontsize=8, ha='center', color='white')

# Queue System
queue_box = FancyBboxPatch((6.6, 2.8), 3.2, 1.2,
                          boxstyle="round,pad=0.05",
                          facecolor=color_queue, edgecolor='black', linewidth=2)
ax.add_patch(queue_box)
ax.text(8.2, 3.6, 'Queue System', fontsize=10, fontweight='bold', ha='center')
ax.text(8.2, 3.3, '• Queue Service', fontsize=8, ha='center')
ax.text(8.2, 3.0, '• Scheduler • Lock Manager', fontsize=8, ha='center')

# Executor System
executor_box = FancyBboxPatch((10, 2.8), 3, 1.2,
                             boxstyle="round,pad=0.05",
                             facecolor=color_service, edgecolor='black', linewidth=2)
ax.add_patch(executor_box)
ax.text(11.5, 3.6, 'Execution System', fontsize=10, fontweight='bold', ha='center', color='white')
ax.text(11.5, 3.3, '• Hybrid Executor', fontsize=8, ha='center', color='white')
ax.text(11.5, 3.0, '• Progress Tracker', fontsize=8, ha='center', color='white')

# Layer 5: Core Engine & Namespace Layer
core_engine_box = FancyBboxPatch((1, 1.2), 6, 1.2,
                                boxstyle="round,pad=0.05",
                                facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(core_engine_box)
ax.text(4, 2.0, 'Core Simulation Engine', fontsize=10, fontweight='bold', ha='center')
ax.text(4, 1.6, 'TracerouteSimulator • PacketTracer • RuleDatabase', fontsize=8, ha='center')

ns_box = FancyBboxPatch((7.5, 1.2), 5.5, 1.2,
                       boxstyle="round,pad=0.05",
                       facecolor=color_core, edgecolor='black', linewidth=2)
ax.add_patch(ns_box)
ax.text(10.25, 2.0, 'Namespace Management', fontsize=10, fontweight='bold', ha='center')
ax.text(10.25, 1.6, 'Network Setup • Service Manager • Host Configuration', fontsize=8, ha='center')

# Data Layer
data_box = FancyBboxPatch((1, 0.1), 12, 0.8,
                         boxstyle="round,pad=0.05",
                         facecolor='#E8E8E8', edgecolor='black', linewidth=2)
ax.add_patch(data_box)
ax.text(7, 0.5, 'Data Layer: Raw Facts • Configuration • Session Storage • Queue Database',
        fontsize=9, ha='center')

# Arrows connecting layers
# Handlers to Services
for x in [1.5, 3, 4.5, 6]:
    arrow = FancyArrowPatch((x, 5.5), (5, 4.0),
                          arrowstyle='->', mutation_scale=10,
                          color='darkgray', linewidth=1.2, alpha=0.7)
    ax.add_patch(arrow)

for x in [7.5, 9, 10.5, 12]:
    arrow = FancyArrowPatch((x, 4.4), (8.2, 4.0),
                          arrowstyle='->', mutation_scale=10,
                          color='darkgray', linewidth=1.2, alpha=0.7)
    ax.add_patch(arrow)

# Services to Core
arrow = FancyArrowPatch((8.2, 2.8), (7, 2.4),
                      arrowstyle='->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((11.5, 2.8), (10.25, 2.4),
                      arrowstyle='->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Core to Data
arrow = FancyArrowPatch((4, 1.2), (4, 0.9),
                      arrowstyle='<->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

arrow = FancyArrowPatch((10.25, 1.2), (10.25, 0.9),
                      arrowstyle='<->', mutation_scale=10,
                      color='darkgray', linewidth=1.5)
ax.add_patch(arrow)

# Add legend
legend_elements = [
    mpatches.Patch(color=color_web, label='Web Server'),
    mpatches.Patch(color=color_wsgi, label='WSGI Application'),
    mpatches.Patch(color=color_handler, label='Request Handlers'),
    mpatches.Patch(color=color_service, label='Core Services'),
    mpatches.Patch(color=color_queue, label='Queue System'),
    mpatches.Patch(color=color_core, label='Core Engine')
]
ax.legend(handles=legend_elements, loc='upper left', fontsize=9)

# Add request flow annotation
ax.text(0.5, 9, 'Request Flow:', fontsize=10, fontweight='bold')
ax.text(0.5, 8.6, '1. HTTP request', fontsize=8)
ax.text(0.5, 8.3, '2. WSGI dispatch', fontsize=8)
ax.text(0.5, 8.0, '3. Handler process', fontsize=8)
ax.text(0.5, 7.7, '4. Service orchestration', fontsize=8)
ax.text(0.5, 7.4, '5. Queue/Execute', fontsize=8)
ax.text(0.5, 7.1, '6. Core simulation', fontsize=8)

# Add SSE annotation
ax.text(13.5, 5.2, 'SSE', fontsize=9, fontweight='bold', rotation=90, ha='center')
ax.text(13.5, 4.6, 'Streams', fontsize=8, rotation=90, ha='center')

plt.tight_layout()
plt.savefig('wsgi_architecture.png', dpi=300, bbox_inches='tight', facecolor='white')
plt.show()

print("WSGI architecture diagram saved as wsgi_architecture.png")
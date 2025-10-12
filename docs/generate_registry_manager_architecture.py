#!/usr/bin/env -S python3 -B -u
"""
Generate architecture diagram for RegistryManager.
Shows layered architecture from applications through RegistryManager to registry files.
"""

from graphviz import Digraph
import sys

def create_architecture_diagram():
    """Create RegistryManager architecture diagram"""

    dot = Digraph(comment='RegistryManager Architecture',
                  format='pdf',
                  engine='dot')

    # Graph attributes for A4 portrait (8.27 x 11.69 inches)
    dot.attr(rankdir='TB',
             size='8,11.5',
             ratio='fill',
             dpi='300',
             splines='ortho',
             nodesep='0.3',
             ranksep='0.5')

    # Default node attributes
    dot.attr('node',
             fontname='Arial',
             fontsize='11',
             style='filled')

    # Default edge attributes
    dot.attr('edge',
             fontname='Arial',
             fontsize='10')

    # ===== APPLICATION LAYER =====
    with dot.subgraph(name='cluster_apps') as c:
        c.attr(label='Application Layer',
               style='dashed',
               color='blue',
               fontsize='14',
               margin='20')

        c.node('apps',
               '''Applications:
• ksms_tester.py
• network_reachability_test_multi.py
• TsimSchedulerService
• batch_command_generator.py''',
               shape='box',
               fillcolor='lightblue',
               width='6')

    # ===== REGISTRY MANAGER =====
    with dot.subgraph(name='cluster_registry_mgr') as c:
        c.attr(label='RegistryManager\n(src/core/registry_manager.py)',
               style='filled,dashed',
               color='darkgreen',
               fillcolor='lightgreen',
               fontsize='14',
               margin='30')

        # Top-level public APIs
        with c.subgraph(name='cluster_public_apis') as s:
            s.attr(label='Public APIs',
                   style='dashed',
                   color='gray',
                   fontsize='12',
                   margin='15')

            s.node('api_host',
                   '''Host Registry Operations
• check_and_register_host()
• unregister_host()
• get_host_info()''',
                   shape='box',
                   fillcolor='lightyellow',
                   width='5.5')

            s.node('api_leases',
                   '''Host Lease Operations
• acquire_source_host_lease()
• release_source_host_lease()
• get_host_lease_count()''',
                   shape='box',
                   fillcolor='lightyellow',
                   width='5.5')

            s.node('api_router',
                   '''Router Lock Operations
• acquire_router_lock()
• release_router_lock()
• acquire_all_router_locks_atomic()''',
                   shape='box',
                   fillcolor='lightyellow',
                   width='5.5')

            s.node('api_waiter',
                   '''Router Waiter Operations
• wait_for_router()
• wait_for_all_routers()''',
                   shape='box',
                   fillcolor='lightyellow',
                   width='5.5')

            s.node('api_neighbor',
                   '''Neighbor Lease Operations
• acquire_neighbor_lease()
• release_neighbor_lease()''',
                   shape='box',
                   fillcolor='lightyellow',
                   width='5.5')

            # Force vertical stacking
            s.edge('api_host', 'api_leases', style='invis')
            s.edge('api_leases', 'api_router', style='invis')
            s.edge('api_router', 'api_waiter', style='invis')
            s.edge('api_waiter', 'api_neighbor', style='invis')

        # Internal components
        with c.subgraph(name='cluster_internal') as s:
            s.attr(label='Internal Components (private)',
                   style='dashed',
                   color='gray',
                   fontsize='12',
                   margin='15')

            s.node('internal_lock',
                   '''_LockManager
• posix_ipc semaphores
• Lock ordering enforcement
• Deadlock prevention''',
                   shape='box',
                   fillcolor='lightcyan',
                   width='5.5')

            s.node('internal_io',
                   '''_RegistryIO
• Atomic read/write + fsync
• Retry on errors
• Corruption handling''',
                   shape='box',
                   fillcolor='lightcyan',
                   width='5.5')

            s.node('internal_tx',
                   '''_Transaction
• Rollback on failure
• Action recording''',
                   shape='box',
                   fillcolor='lightcyan',
                   width='5.5')

            # Force vertical stacking
            s.edge('internal_lock', 'internal_io', style='invis')
            s.edge('internal_io', 'internal_tx', style='invis')

    # ===== REGISTRY FILES =====
    with dot.subgraph(name='cluster_files') as c:
        c.attr(label='Registry Files\n(/dev/shm/tsim/)',
               style='dashed',
               color='darkred',
               fontsize='14',
               margin='20')

        c.node('files',
               '''hosts.json
host_leases.json
neighbor_leases.json
locks/router_*''',
               shape='cylinder',
               fillcolor='mistyrose',
               width='4')

    # ===== CONNECTIONS =====

    # Application to RegistryManager
    dot.edge('apps', 'api_host',
             label='Clean API\n(no lock awareness)',
             style='bold',
             color='blue')

    # Connect public APIs to internal components (invisible for layout)
    dot.edge('api_neighbor', 'internal_lock', style='invis')

    # Internal components to files
    dot.edge('internal_io', 'files',
             label='Atomic I/O + locks',
             color='darkgreen',
             style='bold')

    # ===== LEGEND =====
    legend_html = '''<
<TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
  <TR><TD COLSPAN="2" BGCOLOR="lightgray"><B>LEGEND</B></TD></TR>
  <TR>
    <TD BGCOLOR="lightblue">Applications</TD>
    <TD BGCOLOR="lightyellow">Public APIs</TD>
  </TR>
  <TR>
    <TD BGCOLOR="lightcyan">Internal Components</TD>
    <TD BGCOLOR="mistyrose">Registry Files</TD>
  </TR>
</TABLE>>'''

    dot.node('legend_table',
             label=legend_html,
             shape='plaintext')

    # Position legend at bottom
    with dot.subgraph() as s:
        s.attr(rank='sink')
        s.node('legend_table')

    dot.edge('files', 'legend_table', style='invis', weight='100')

    return dot

def main():
    """Generate and save architecture diagram"""
    print("Generating RegistryManager architecture diagram...")

    dot = create_architecture_diagram()

    # Save to files
    output_base = '/home/sparavec/git/traceroute-simulator/docs/registry_manager_architecture_diagram'

    try:
        # Render to PDF (best for printing)
        dot.render(output_base, format='pdf', cleanup=True)
        print(f"✓ Generated: {output_base}.pdf")

        # Also render to PNG for preview
        dot.render(output_base, format='png', cleanup=False)
        print(f"✓ Generated: {output_base}.png")

        # Save source
        with open(f"{output_base}.dot", 'w') as f:
            f.write(dot.source)
        print(f"✓ Generated: {output_base}.dot (source)")

        print("\nArchitecture diagram generated successfully!")

    except Exception as e:
        print(f"ERROR: Failed to generate diagram: {e}", file=sys.stderr)
        print("Make sure graphviz is installed: sudo apt-get install graphviz", file=sys.stderr)
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())

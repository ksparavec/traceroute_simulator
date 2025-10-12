#!/usr/bin/env -S python3 -B -u
"""
Generate comprehensive flowchart for job scheduling with race condition elimination.
Depicts the entire flow from job submission through execution to cleanup.
"""

from graphviz import Digraph
import sys

def create_flowchart():
    """Create comprehensive scheduling flowchart"""

    # Create digraph with optimized settings for A3 paper
    dot = Digraph(comment='Job Scheduling Flow with Race Condition Elimination',
                  format='pdf',
                  engine='dot')

    # Graph attributes for A3 paper (11.69 x 16.54 inches)
    dot.attr(rankdir='TB',  # Top to bottom
             ratio='compress',  # Minimize whitespace
             dpi='300',
             fontname='Arial',
             fontsize='10',
             nodesep='0.15',  # Minimal horizontal spacing
             ranksep='0.3',   # Minimal vertical spacing
             splines='ortho',  # Orthogonal edges for clarity
             bgcolor='white')

    # Default node attributes
    dot.attr('node',
             fontname='Arial',
             fontsize='9',
             style='filled',
             fillcolor='lightblue',
             shape='box')

    # Default edge attributes
    dot.attr('edge',
             fontname='Arial',
             fontsize='8')

    # ===== JOB SUBMISSION =====
    with dot.subgraph(name='cluster_submission') as c:
        c.attr(label='Job Submission', style='dashed', color='gray', margin='4')

        c.node('start', 'User Submits Job\n(Quick or Detailed)',
               shape='ellipse', fillcolor='lightgreen')
        c.node('submit', 'Handler receives request\nGenerates run_id',
               fillcolor='lightyellow')
        c.node('enqueue', 'Enqueue job to\nTsimQueueService\n(FIFO, simple)',
               fillcolor='lightyellow')

    dot.edge('start', 'submit')
    dot.edge('submit', 'enqueue')

    # ===== SCHEDULER =====
    with dot.subgraph(name='cluster_scheduler') as c:
        c.attr(label='Router-Agnostic Scheduler', style='dashed', color='blue', margin='4')

        c.node('sched_loop', 'Scheduler Leader Loop\n(no global lock,\nno router tracking)',
               fillcolor='lightcyan')
        c.node('sched_cleanup', 'Cleanup completed jobs',
               fillcolor='lightcyan')
        c.node('sched_count', 'Count running\nquick jobs',
               shape='parallelogram',
               fillcolor='lightcyan')
        c.node('sched_decide', 'Can start\nmore jobs?',
               shape='diamond',
               fillcolor='yellow')
        c.node('sched_pop', 'Pop jobs from queue\n(Quick jobs PRIORITY,\nrespects DSCP limit)',
               fillcolor='lightcyan')
        c.node('sched_allocate', 'Allocate DSCP\nfor quick jobs',
               fillcolor='lightcyan')
        c.node('sched_submit', 'Submit to\nthread pool',
               fillcolor='lightcyan')

    dot.edge('enqueue', 'sched_loop')
    dot.edge('sched_loop', 'sched_cleanup')
    dot.edge('sched_cleanup', 'sched_count')
    dot.edge('sched_count', 'sched_decide')
    dot.edge('sched_decide', 'sched_pop', label='Yes')
    dot.edge('sched_decide', 'sched_loop', label='No (wait)', style='dashed')
    dot.edge('sched_pop', 'sched_allocate')
    dot.edge('sched_allocate', 'sched_submit')

    # ===== JOB TYPE DECISION =====
    dot.node('job_type', 'Job Type?',
             shape='diamond',
             fillcolor='yellow')

    dot.edge('sched_submit', 'job_type')

    # ===== QUICK JOB FLOW =====
    with dot.subgraph(name='cluster_quick') as c:
        c.attr(label='Quick Job Execution (Parallel, DSCP Isolated)',
               style='dashed', color='green', margin='4')

        c.node('quick_start', 'Quick Job Starts\n(has unique DSCP)',
               shape='ellipse',
               fillcolor='lightgreen')
        quick_wait_label = '''<
For each router:<BR/>
RouterWaiter.wait_until_free()<BR/>
(inotify, no polling)<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="#000099"><B>→ RegistryManager:</B></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">  wait_for_router(router, timeout)</FONT>>'''
        c.node('quick_wait', label=quick_wait_label,
               fillcolor='palegreen')
        c.node('quick_locked', 'Router locked\nby detailed job?',
               shape='diamond',
               fillcolor='yellow')
        c.node('quick_block', 'Block until\nlock released\n(inotify wakeup)',
               fillcolor='orange')
        quick_hosts_label = '''<
Create/acquire<BR/>
source hosts<BR/>
(physical + lease)<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="#000099"><B>→ RegistryManager:</B></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">  check_and_register_host(...)</FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">  acquire_source_host_lease(</FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">    run_id, host, 'quick', router, dscp)</FONT>>'''
        c.node('quick_hosts', label=quick_hosts_label,
               fillcolor='palegreen')
        c.node('quick_iptables', 'Install iptables rules\n(--noflush, DSCP-specific)',
               fillcolor='palegreen')
        c.node('quick_test', 'Run tests\n(DSCP isolated)',
               fillcolor='palegreen')
        c.node('quick_cleanup_ipt', 'Cleanup iptables\n(--noflush, DSCP-specific)',
               fillcolor='palegreen')
        quick_cleanup_hosts_label = '''<
Release source host leases<BR/>
ref_count--<BR/>
Delete if ref_count==0<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="#000099"><B>→ RegistryManager:</B></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">  ref_count, should_delete =</FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">    release_source_host_lease(</FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">      run_id, host)</FONT>>'''
        c.node('quick_cleanup_hosts', label=quick_cleanup_hosts_label,
               fillcolor='palegreen')
        c.node('quick_end', 'Quick Job Complete',
               shape='ellipse',
               fillcolor='lightgreen')

    dot.edge('job_type', 'quick_start')
    dot.edge('quick_start', 'quick_wait')
    dot.edge('quick_wait', 'quick_locked')
    dot.edge('quick_locked', 'quick_block', label='Yes')
    dot.edge('quick_block', 'quick_locked', label='Check again')
    dot.edge('quick_locked', 'quick_hosts', label='No (free)')
    dot.edge('quick_hosts', 'quick_iptables')
    dot.edge('quick_iptables', 'quick_test')
    dot.edge('quick_test', 'quick_cleanup_ipt')
    dot.edge('quick_cleanup_ipt', 'quick_cleanup_hosts')
    dot.edge('quick_cleanup_hosts', 'quick_end')

    # ===== DETAILED JOB FLOW =====
    with dot.subgraph(name='cluster_detailed') as c:
        c.attr(label='Detailed Job Execution (All Routers in Parallel, Exclusive Access)',
               style='dashed', color='red', margin='4')

        c.node('det_start', 'Detailed Job Starts',
               shape='ellipse',
               fillcolor='mistyrose')
        c.node('det_check_locks', 'ALL routers\navailable?',
               shape='diamond',
               fillcolor='yellow')
        c.node('det_block', 'Wait for ALL routers\nto be released\n(retry lock acquisition)',
               fillcolor='orange')
        det_lock_all_label = '''<
Acquire ALL router locks<BR/>
ATOMICALLY<BR/>
(all-or-nothing)<BR/>
[DEADLOCK PREVENTION]<BR/>
Grants exclusive access<BR/>
to all routers + hosts<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="#000099"><B>→ RegistryManager:</B></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">  with all_router_locks(</FONT><BR/>
<FONT POINT-SIZE="8" COLOR="#000099">    routers, job_id, timeout):</FONT>>'''
        c.node('det_lock_all', label=det_lock_all_label,
               fillcolor='mistyrose')
        det_src_hosts_label = '''<
Create/acquire<BR/>
source hosts<BR/>
(physical + lease)<BR/>
[tsimsh parallel]<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I><B>RegistryManager:</B></I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>check_and_register_host(...)</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>acquire_source_host_lease(</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>  run_id, host, 'detailed', router)</I></FONT>>'''
        c.node('det_src_hosts', label=det_src_hosts_label,
               fillcolor='mistyrose')
        c.node('det_dst_hosts', 'Create destination hosts\n(ephemeral, no lease)\n[tsimsh parallel]',
               fillcolor='mistyrose')
        c.node('det_services', 'Create and start\nservices on\ndestination hosts\n[tsimsh parallel]',
               fillcolor='mistyrose')
        c.node('det_baseline', 'Read baseline\nFORWARD counters\n[all routers]',
               fillcolor='mistyrose')
        c.node('det_test', 'Send test traffic\n[all routers]',
               fillcolor='mistyrose')
        c.node('det_final', 'Read final\nFORWARD counters\n[all routers]',
               fillcolor='mistyrose')
        c.node('det_calc', 'Calculate delta\n(no pollution)\n[all routers]',
               fillcolor='mistyrose')
        c.node('det_cleanup_services', 'Stop and cleanup\nservices\n[tsimsh parallel]',
               fillcolor='mistyrose')
        c.node('det_cleanup_dst', 'Delete destination hosts\n(ephemeral)\n[tsimsh parallel]',
               fillcolor='mistyrose')
        det_cleanup_src_label = '''<
Release source host leases<BR/>
ref_count--<BR/>
Delete if ref_count==0<BR/>
[all hosts]<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I><B>RegistryManager:</B></I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>ref_count, should_delete =</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>  release_source_host_lease(</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>    run_id, host)</I></FONT>>'''
        c.node('det_cleanup_src', label=det_cleanup_src_label,
               fillcolor='mistyrose')
        det_unlock_all_label = '''<
Release ALL router locks<BR/>
ATOMICALLY<BR/>
(touch notify files)<BR/>
[wake all waiters]<BR/>
<BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I><B>RegistryManager:</B></I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>// context manager exit:</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>release_all_router_locks(</I></FONT><BR/>
<FONT POINT-SIZE="8" COLOR="darkblue"><I>  routers, job_id)</I></FONT>>'''
        c.node('det_unlock_all', label=det_unlock_all_label,
               fillcolor='mistyrose')
        c.node('det_end', 'Detailed Job Complete',
               shape='ellipse',
               fillcolor='mistyrose')

    dot.edge('job_type', 'det_start')
    dot.edge('det_start', 'det_check_locks')
    dot.edge('det_check_locks', 'det_block', label='No (any locked)')
    dot.edge('det_block', 'det_check_locks', label='Retry')
    dot.edge('det_check_locks', 'det_lock_all', label='Yes (all free)')
    dot.edge('det_lock_all', 'det_src_hosts')
    dot.edge('det_src_hosts', 'det_dst_hosts')
    dot.edge('det_dst_hosts', 'det_services')
    dot.edge('det_services', 'det_baseline')
    dot.edge('det_baseline', 'det_test')
    dot.edge('det_test', 'det_final')
    dot.edge('det_final', 'det_calc')
    dot.edge('det_calc', 'det_cleanup_services')
    dot.edge('det_cleanup_services', 'det_cleanup_dst')
    dot.edge('det_cleanup_dst', 'det_cleanup_src')
    dot.edge('det_cleanup_src', 'det_unlock_all')
    dot.edge('det_unlock_all', 'det_end')

    # Note: Router lock coordination and lease registry details are described
    # in the node labels themselves (e.g., "Acquire ALL router locks ATOMICALLY")
    # Removed separate coordination boxes to keep flowchart clean

    # ===== COMPLETION PATHS =====
    dot.node('complete', 'Return results\nto user',
             shape='ellipse',
             fillcolor='lightgreen')

    dot.edge('quick_end', 'complete')
    dot.edge('det_end', 'complete')
    dot.edge('complete', 'sched_loop', label='Scheduler continues', style='dashed')

    # ===== LEGEND (at bottom center) =====
    # Create legend as HTML table for better formatting
    legend_html = '''<
<TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">
  <TR><TD COLSPAN="6" BGCOLOR="lightgray"><B>LEGEND</B></TD></TR>
  <TR>
    <TD BGCOLOR="lightgreen">Quick Job<BR/>Start/End</TD>
    <TD BGCOLOR="palegreen">Quick Job<BR/>Process</TD>
    <TD BGCOLOR="mistyrose">Detailed Job<BR/>(all boxes)</TD>
    <TD BGCOLOR="yellow">Decision<BR/>(diamond)</TD>
    <TD BGCOLOR="orange">Blocking<BR/>(waiting)</TD>
    <TD BGCOLOR="lightblue">Scheduler<BR/>Process</TD>
  </TR>
</TABLE>>'''

    dot.node('legend_table',
             label=legend_html,
             shape='plaintext')

    # Position legend at bottom
    with dot.subgraph() as s:
        s.attr(rank='sink')
        s.node('legend_table')

    # Connect from complete to legend with strong weight
    dot.edge('complete', 'legend_table', style='invis', weight='100')

    return dot

def main():
    """Generate and save flowchart"""
    print("Generating comprehensive scheduling flowchart...")

    dot = create_flowchart()

    # Save to files
    output_base = '/home/sparavec/git/traceroute-simulator/docs/job_scheduling_flowchart'

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

        print("\nFlowchart generated successfully!")
        print(f"Print the PDF on A3 paper for best results: {output_base}.pdf")

    except Exception as e:
        print(f"ERROR: Failed to generate flowchart: {e}", file=sys.stderr)
        print("Make sure graphviz is installed: sudo apt-get install graphviz", file=sys.stderr)
        return 1

    return 0

if __name__ == '__main__':
    sys.exit(main())

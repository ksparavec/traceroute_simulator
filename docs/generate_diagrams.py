#!/usr/bin/env -S python3 -B -u
"""
Generate architecture and flow diagrams for documentation.
Creates both ASCII art and GraphViz diagrams.
"""

import os
import sys
import subprocess
from pathlib import Path

def create_architecture_diagram():
    """Create system architecture diagram using GraphViz."""
    
    dot_content = """
    digraph Architecture {
        rankdir=TB;
        node [shape=box, style=rounded];
        
        // User Interface Layer
        subgraph cluster_ui {
            label="User Interfaces";
            style=filled;
            color=lightgrey;
            
            web [label="Web Interface\\n(Apache + CGI)"];
            tsimsh [label="tsimsh\\n(Interactive Shell)"];
            cli [label="Command Line\\n(Direct Scripts)"];
            ansible [label="Ansible\\n(Remote Collection)"];
        }
        
        // Core Engine Layer
        subgraph cluster_core {
            label="Core Python Engine";
            style=filled;
            color=lightblue;
            
            simulator [label="TracerouteSimulator\\n(Path Calculation)"];
            analyzer [label="IptablesAnalyzer\\n(Firewall Rules)"];
            namespace [label="NamespaceManager\\n(Virtual Networks)"];
            service [label="ServiceManager\\n(TCP/UDP Testing)"];
            packet [label="PacketTracer\\n(Packet Flow)"];
        }
        
        // Data Layer
        subgraph cluster_data {
            label="Data Storage";
            style=filled;
            color=lightyellow;
            
            facts [label="Router Facts\\n(JSON Files)"];
            raw [label="Raw Facts\\n(Text Files)"];
            topology [label="Network Topology\\n(Connections)"];
            registry [label="Host Registry\\n(Dynamic Hosts)"];
        }
        
        // Infrastructure Layer
        subgraph cluster_infra {
            label="Linux Infrastructure";
            style=filled;
            color=lightgreen;
            
            netns [label="Network Namespaces"];
            iptables [label="iptables/netfilter"];
            iproute [label="iproute2"];
            processes [label="Process Management"];
        }
        
        // Connections
        web -> simulator;
        tsimsh -> simulator;
        tsimsh -> namespace;
        tsimsh -> service;
        cli -> simulator;
        cli -> analyzer;
        ansible -> facts;
        
        simulator -> analyzer;
        simulator -> packet;
        simulator -> facts;
        analyzer -> facts;
        analyzer -> raw;
        
        namespace -> netns;
        namespace -> iptables;
        namespace -> iproute;
        service -> processes;
        service -> registry;
        
        packet -> topology;
        packet -> facts;
    }
    """
    
    return dot_content

def create_data_flow_diagram():
    """Create data flow diagram for a trace operation."""
    
    dot_content = """
    digraph DataFlow {
        rankdir=LR;
        node [shape=box, style=rounded];
        
        // Start
        user [label="User Request\\n(Source + Dest IP)", shape=ellipse, style=filled, fillcolor=lightgreen];
        
        // Processing steps
        input [label="Input Validation"];
        load [label="Load Router Facts"];
        source [label="Find Source Router"];
        calc [label="Calculate Path"];
        firewall [label="Analyze Firewall Rules"];
        mtr [label="Execute MTR\\n(Optional)"];
        format [label="Format Output"];
        
        // End
        result [label="Result\\n(Path + Status)", shape=ellipse, style=filled, fillcolor=lightcoral];
        
        // Flow
        user -> input;
        input -> load;
        load -> source;
        source -> calc;
        calc -> firewall;
        firewall -> mtr [label="if external"];
        firewall -> format [label="if internal"];
        mtr -> format;
        format -> result;
        
        // Data stores
        facts_db [label="Facts Directory", shape=cylinder];
        raw_db [label="Raw Facts", shape=cylinder];
        
        load -> facts_db [style=dashed];
        firewall -> raw_db [style=dashed, label="packet counts"];
    }
    """
    
    return dot_content

def create_namespace_diagram():
    """Create network namespace topology diagram."""
    
    dot_content = """
    digraph Namespaces {
        rankdir=TB;
        compound=true;
        
        // Namespace boxes
        subgraph cluster_hq {
            label="HQ Network";
            style=filled;
            color=lightblue;
            
            hq_gw [label="hq-gw\\n10.1.1.1"];
            hq_core [label="hq-core\\n10.1.2.1"];
            hq_dmz [label="hq-dmz\\n10.1.3.1"];
            hq_lab [label="hq-lab\\n10.1.4.1"];
            
            hq_gw -> hq_core [label="eth1"];
            hq_core -> hq_dmz [label="eth2"];
            hq_core -> hq_lab [label="eth3"];
        }
        
        subgraph cluster_branch {
            label="Branch Network";
            style=filled;
            color=lightgreen;
            
            br_gw [label="br-gw\\n10.2.1.1"];
            br_core [label="br-core\\n10.2.1.2"];
            br_wifi [label="br-wifi\\n10.2.1.3"];
            
            br_gw -> br_core [label="eth1"];
            br_core -> br_wifi [label="eth2"];
        }
        
        subgraph cluster_dc {
            label="Data Center";
            style=filled;
            color=lightyellow;
            
            dc_gw [label="dc-gw\\n10.3.1.1"];
            dc_core [label="dc-core\\n10.3.1.2"];
            dc_srv [label="dc-srv\\n10.3.1.3"];
            
            dc_gw -> dc_core [label="eth1"];
            dc_core -> dc_srv [label="eth2"];
        }
        
        // VPN connections
        hq_gw -> br_gw [label="WireGuard\\nwg0", style=dashed, color=red];
        hq_gw -> dc_gw [label="WireGuard\\nwg1", style=dashed, color=red];
        br_gw -> dc_gw [label="WireGuard\\nwg1", style=dashed, color=red];
    }
    """
    
    return dot_content

def create_command_hierarchy():
    """Create tsimsh command hierarchy diagram."""
    
    dot_content = """
    digraph Commands {
        rankdir=TB;
        node [shape=box, style=rounded];
        
        tsimsh [label="tsimsh", shape=ellipse, style=filled, fillcolor=lightblue];
        
        // Command categories
        trace_cat [label="trace", style=filled, fillcolor=lightyellow];
        network_cat [label="network", style=filled, fillcolor=lightyellow];
        service_cat [label="service", style=filled, fillcolor=lightyellow];
        host_cat [label="host", style=filled, fillcolor=lightyellow];
        facts_cat [label="facts", style=filled, fillcolor=lightyellow];
        
        // Trace commands
        trace_basic [label="trace -s IP -d IP"];
        trace_port [label="trace ... -p tcp -dp PORT"];
        trace_json [label="trace ... -j"];
        
        // Network commands
        net_setup [label="network setup"];
        net_status [label="network status"];
        net_clean [label="network clean"];
        
        // Service commands
        svc_start [label="service start"];
        svc_test [label="service test"];
        svc_stop [label="service stop"];
        svc_list [label="service list"];
        
        // Host commands
        host_add [label="host add"];
        host_del [label="host del"];
        host_list [label="host list"];
        
        // Facts commands
        facts_process [label="facts process"];
        facts_update [label="facts update"];
        facts_show [label="facts show"];
        
        // Hierarchy
        tsimsh -> trace_cat;
        tsimsh -> network_cat;
        tsimsh -> service_cat;
        tsimsh -> host_cat;
        tsimsh -> facts_cat;
        
        trace_cat -> trace_basic;
        trace_cat -> trace_port;
        trace_cat -> trace_json;
        
        network_cat -> net_setup;
        network_cat -> net_status;
        network_cat -> net_clean;
        
        service_cat -> svc_start;
        service_cat -> svc_test;
        service_cat -> svc_stop;
        service_cat -> svc_list;
        
        host_cat -> host_add;
        host_cat -> host_del;
        host_cat -> host_list;
        
        facts_cat -> facts_process;
        facts_cat -> facts_update;
        facts_cat -> facts_show;
    }
    """
    
    return dot_content

def generate_diagram(name, dot_content, output_dir):
    """Generate diagram from DOT content."""
    
    # Create output directory if needed
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write DOT file
    dot_file = output_dir / f"{name}.dot"
    with open(dot_file, 'w') as f:
        f.write(dot_content)
    
    # Generate PNG if graphviz is available
    try:
        png_file = output_dir / f"{name}.png"
        subprocess.run(['dot', '-Tpng', str(dot_file), '-o', str(png_file)], 
                      check=True, capture_output=True)
        print(f"Generated: {png_file}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"Generated DOT file: {dot_file}")
        print("Install graphviz to generate PNG: apt-get install graphviz")
    
    # Generate SVG for web viewing
    try:
        svg_file = output_dir / f"{name}.svg"
        subprocess.run(['dot', '-Tsvg', str(dot_file), '-o', str(svg_file)], 
                      check=True, capture_output=True)
        print(f"Generated: {svg_file}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

def main():
    """Generate all documentation diagrams."""
    
    # Determine output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir / "diagrams"
    
    print("Generating documentation diagrams...")
    
    # Generate each diagram
    diagrams = [
        ("architecture", create_architecture_diagram()),
        ("data_flow", create_data_flow_diagram()),
        ("namespace_topology", create_namespace_diagram()),
        ("command_hierarchy", create_command_hierarchy()),
    ]
    
    for name, content in diagrams:
        generate_diagram(name, content, output_dir)
    
    print(f"\nDiagrams generated in: {output_dir}")
    print("\nTo view DOT files as text:")
    print(f"  cat {output_dir}/*.dot")
    print("\nTo generate images (requires graphviz):")
    print("  apt-get install graphviz")
    print(f"  dot -Tpng {output_dir}/architecture.dot -o {output_dir}/architecture.png")

if __name__ == "__main__":
    main()
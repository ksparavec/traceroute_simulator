#!/usr/bin/env -S python3 -B -u
"""
Network Namespace Status Tool v2

Refactored version using the new modular network_status package
with caching and parallel execution support.

This is a wrapper script that maintains backward compatibility
with the original network_namespace_status.py interface.
"""

import argparse
import json
import logging
import os
import sys

# Add parent directories to path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)
project_dir = os.path.dirname(src_dir)
sys.path.insert(0, project_dir)
sys.path.insert(0, src_dir)

# When run as external script, we need relative imports
# But we also need to handle the tsim imports in the modules
import sys
original_meta_path = sys.meta_path.copy()

try:
    # First try direct import
    from simulators.network_status.manager import NetworkStatusManager
    from simulators.network_status.exceptions import ConfigurationError
except ImportError:
    # If that fails, try with tsim prefix
    # This shouldn't happen when run as script but keeping for safety
    from tsim.simulators.network_status import NetworkStatusManager
    from tsim.simulators.network_status.exceptions import ConfigurationError


def main():
    """Main entry point for network status tool."""
    parser = argparse.ArgumentParser(
        description="Show network namespace status with caching and parallel execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary                          # Overview of all namespaces (default)
  %(prog)s interfaces --limit hq-gw         # Interface config for specific router
  %(prog)s routes --limit br-core           # Routing table for specific router
  %(prog)s summary --limit "hq-*"           # Summary for routers matching pattern
  %(prog)s rules --limit "*-core"           # Policy rules for core routers
  %(prog)s all --limit dc-srv               # Complete config for router
  %(prog)s summary --no-cache               # Bypass cache for fresh data
  %(prog)s summary --invalidate-cache       # Clear cache before query
  %(prog)s summary --cache-stats            # Show cache statistics

Functions:
  interfaces  - IP configuration (ip addr show equivalent)
  routes      - Routing tables (ip route show equivalent)
  rules       - Policy rules (ip rule show equivalent)
  iptables    - Iptables configuration
  ipsets      - Ipset configuration
  summary     - Brief overview (default)
  all         - Complete configuration

Performance Options:
  --no-cache            Bypass cache and fetch fresh data
  --invalidate-cache    Clear cache before query
  --warm-cache          Pre-populate cache for all namespaces
  --cache-stats         Show cache statistics
  --no-parallel         Disable parallel execution (for debugging)

Limit Options:
  --limit <pattern>  - Limit to specific namespaces (supports glob patterns)
                       Examples: "hq-gw", "br-*", "*-core"
        """
    )
    
    parser.add_argument(
        'function',
        type=str,
        nargs='?',
        default='summary',
        choices=['interfaces', 'routes', 'rules', 'iptables', 'ipsets', 'summary', 'all'],
        help='Information to display (default: summary)'
    )
    
    parser.add_argument(
        '--limit',
        type=str,
        help='Limit to specific namespaces (supports glob patterns)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity: -v (errors), -vv (info), -vvv (debug)'
    )
    
    parser.add_argument(
        '-j', '--json',
        action='store_true',
        help='Output in JSON format'
    )
    
    # Cache control options
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Bypass cache and fetch fresh data'
    )
    
    parser.add_argument(
        '--invalidate-cache',
        action='store_true',
        help='Clear cache before query'
    )
    
    parser.add_argument(
        '--warm-cache',
        action='store_true',
        help='Pre-populate cache for all matching namespaces'
    )
    
    parser.add_argument(
        '--cache-stats',
        action='store_true',
        help='Show cache statistics'
    )
    
    # Performance options
    parser.add_argument(
        '--no-parallel',
        action='store_true',
        help='Disable parallel execution (for debugging)'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize manager with configuration (no facts_dir needed)
        manager = NetworkStatusManager(
            config_path=args.config,
            verbose=args.verbose
        )
        
        # Handle cache operations
        if args.invalidate_cache:
            manager.invalidate_cache()
            if not args.json:
                print("Cache invalidated")
        
        if args.warm_cache:
            manager.warm_cache(pattern=args.limit)
            if not args.json:
                print("Cache warmed")
            if not args.cache_stats:
                return
        
        if args.cache_stats:
            stats = manager.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                cache_stats = stats.get('cache', {})
                print("=== CACHE STATISTICS ===")
                print(f"  Enabled: {cache_stats.get('enabled', False)}")
                print(f"  Hits: {stats.get('cache_hits', 0)}")
                print(f"  Misses: {stats.get('cache_misses', 0)}")
                print(f"  Entries: {cache_stats.get('entries', 0)}")
                print(f"  Size: {cache_stats.get('size_mb', 0)} MB")
                print(f"  Path: {cache_stats.get('path', 'N/A')}")
                
                collector_stats = stats.get('collector', {})
                print("\n=== COLLECTOR STATISTICS ===")
                print(f"  Namespaces queried: {collector_stats.get('namespaces_queried', 0)}")
                print(f"  Successful queries: {collector_stats.get('successful_queries', 0)}")
                print(f"  Failed queries: {collector_stats.get('failed_queries', 0)}")
                print(f"  Timeouts: {collector_stats.get('timeouts', 0)}")
                print(f"  Avg time per namespace: {collector_stats.get('avg_time_per_namespace', 0):.3f}s")
            return
        
        # Disable parallel if requested
        if args.no_parallel:
            manager.config.config['parallelization']['enabled'] = False
            manager.collector.parallel_enabled = False
        
        # Get status
        output = manager.get_status(
            function=args.function,
            limit_pattern=args.limit,
            use_cache=not args.no_cache,
            output_format='json' if args.json else 'text'
        )
        
        print(output)
        
    except ConfigurationError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"Status check failed: {str(e)}"}))
        else:
            print(f"Status check failed: {e}", file=sys.stderr)
            if args.verbose >= 3:
                import traceback
                traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
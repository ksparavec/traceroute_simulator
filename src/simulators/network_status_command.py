#!/usr/bin/env -S python3 -B -u
"""
Completely isolated network status runner.

This script runs in a completely separate Python interpreter to ensure
no interference with the parent process's readline state.
"""

import sys
import os
import json
import argparse

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument('function', default='summary')
    parser.add_argument('--limit', type=str, default=None)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--table', action='store_true')
    parser.add_argument('--verbose', '-v', action='count', default=0)
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--invalidate-cache', action='store_true')
    parser.add_argument('--cache-stats', action='store_true')
    parser.add_argument('--timeout', type=int, metavar='SECONDS',
                        help='Timeout per namespace in seconds (default: 5)')
    
    args = parser.parse_args()
    
    # Set PYTHONDONTWRITEBYTECODE to prevent .pyc files
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    
    # Now import the module in this isolated process
    try:
        from tsim.simulators.network_status import NetworkStatusManager
        
        # Initialize manager
        manager = NetworkStatusManager(verbose=args.verbose, timeout=args.timeout)
        
        # Handle cache operations
        if args.invalidate_cache:
            manager.invalidate_cache()
            if not args.json:
                print("[SUCCESS] Cache invalidated")
            if not args.cache_stats and args.function == 'summary':
                return 0
        
        if args.cache_stats:
            stats = manager.get_stats()
            if args.json:
                print(json.dumps(stats, indent=2))
            else:
                cache_stats = stats.get('cache', {})
                print("=== CACHE STATISTICS ===")
                print(f"  Enabled: {cache_stats.get('enabled', False)}")
                print(f"  Hits: {cache_stats.get('hits', 0)}")
                print(f"  Misses: {cache_stats.get('misses', 0)}")
                print(f"  Entries: {cache_stats.get('entries', 0)}")
                print(f"  Size: {cache_stats.get('size_mb', 0):.2f} MB")
            return 0
        
        # Get status
        if args.json:
            output_format = 'json'
        elif args.table:
            output_format = 'table'
        else:
            output_format = 'text'
            
        output = manager.get_status(
            function=args.function,
            limit_pattern=args.limit,
            use_cache=not args.no_cache,
            output_format=output_format
        )
        
        print(output)
        return 0
        
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"[ERROR] {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
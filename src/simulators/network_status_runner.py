#!/usr/bin/env -S python3 -B -u
"""
Network Status Runner - Subprocess isolation wrapper

This script is executed in a subprocess to prevent any interference
with the parent tsimsh process's readline/cmd2 state.
"""

import sys
import json
import argparse

def main():
    """Main entry point for subprocess execution."""
    parser = argparse.ArgumentParser()
    parser.add_argument('function', default='summary')
    parser.add_argument('--limit', type=str, default=None)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', '-v', action='count', default=0)
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--invalidate-cache', action='store_true')
    parser.add_argument('--cache-stats', action='store_true')
    
    args = parser.parse_args()
    
    # Import here, in isolated subprocess
    from tsim.simulators.network_status import NetworkStatusManager
    
    try:
        # Initialize manager
        manager = NetworkStatusManager(verbose=args.verbose)
        
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
                print(f"  Hits: {stats.get('cache_hits', 0)}")
                print(f"  Misses: {stats.get('cache_misses', 0)}")
                print(f"  Entries: {cache_stats.get('entries', 0)}")
                print(f"  Size: {cache_stats.get('size_mb', 0)} MB")
            return 0
        
        # Get status
        output = manager.get_status(
            function=args.function,
            limit_pattern=args.limit,
            use_cache=not args.no_cache,
            output_format='json' if args.json else 'text'
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
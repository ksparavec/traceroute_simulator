#!/usr/bin/env python3
"""
process_all_facts.py - Batch process all raw facts files to JSON format

This script processes all raw facts files from the configured raw facts directory
and converts them to structured JSON format in the configured JSON facts directory.
It uses environment variables to determine source and destination paths.

Environment Variables:
    TRACEROUTE_SIMULATOR_RAW_FACTS: Directory containing raw facts files (default: raw_facts)
    TRACEROUTE_SIMULATOR_FACTS: Directory for output JSON files (default: tsim_facts)

Usage:
    # Process all raw facts files
    python3 process_all_facts.py
    
    # Process with verbose output
    python3 process_all_facts.py --verbose
    
    # Process with raw data preservation
    python3 process_all_facts.py --raw
    
    # Process with pretty JSON formatting
    python3 process_all_facts.py --pretty
    
    # Process specific files only
    python3 process_all_facts.py --files router1_facts.txt router2_facts.txt
"""

import os
import sys
import argparse
import json
import glob
from pathlib import Path
from typing import List, Dict, Any

# Add current directory to path to import process_facts
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from process_facts import FactsProcessor
except ImportError as e:
    print(f"Error: Could not import process_facts module: {e}")
    sys.exit(1)


def get_facts_directories() -> tuple[str, str]:
    """
    Get source and destination directories from environment variables.
    
    Returns:
        Tuple of (raw_facts_dir, json_facts_dir)
    """
    raw_facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_RAW_FACTS', 'raw_facts')
    json_facts_dir = os.environ.get('TRACEROUTE_SIMULATOR_FACTS', 'tsim_facts')
    
    return raw_facts_dir, json_facts_dir


def find_raw_facts_files(raw_facts_dir: str, specific_files: List[str] = None) -> List[str]:
    """
    Find all raw facts files in the specified directory.
    
    Args:
        raw_facts_dir: Directory containing raw facts files
        specific_files: Optional list of specific files to process
        
    Returns:
        List of raw facts file paths
    """
    if specific_files:
        # Process only specified files
        files = []
        for filename in specific_files:
            file_path = os.path.join(raw_facts_dir, filename)
            if os.path.exists(file_path):
                files.append(file_path)
            else:
                print(f"Warning: File not found: {file_path}")
        return files
    
    # Find all *_facts.txt files
    pattern = os.path.join(raw_facts_dir, '*_facts.txt')
    files = glob.glob(pattern)
    
    # Sort files for consistent processing order
    files.sort()
    
    return files


def get_output_filename(raw_facts_file: str, json_facts_dir: str) -> str:
    """
    Generate output JSON filename from raw facts filename.
    
    Args:
        raw_facts_file: Path to raw facts file
        json_facts_dir: Directory for output JSON files
        
    Returns:
        Path to output JSON file
    """
    basename = os.path.basename(raw_facts_file)
    
    # Convert router_facts.txt to router.json
    if basename.endswith('_facts.txt'):
        json_name = basename[:-10] + '.json'  # Remove '_facts.txt', add '.json'
    else:
        json_name = basename + '.json'
    
    return os.path.join(json_facts_dir, json_name)


def process_single_file(raw_facts_file: str, json_facts_file: str, 
                       processor: FactsProcessor, verbose: bool = False) -> Dict[str, Any]:
    """
    Process a single raw facts file to JSON format.
    
    Args:
        raw_facts_file: Path to raw facts file
        json_facts_file: Path to output JSON file
        processor: FactsProcessor instance
        verbose: Enable verbose output
        
    Returns:
        Dictionary containing processing results
    """
    result = {
        'raw_file': raw_facts_file,
        'json_file': json_facts_file,
        'success': False,
        'error': None,
        'hostname': None,
        'sections': 0
    }
    
    try:
        if verbose:
            print(f"Processing {raw_facts_file}...")
        
        # Parse the raw facts file
        facts = processor.parse_facts_file(raw_facts_file)
        
        # Extract metadata for reporting
        result['hostname'] = facts.get('metadata', {}).get('hostname', 'unknown')
        result['sections'] = len(facts.get('metadata', {}).get('sections_available', []))
        
        # Write JSON output
        with open(json_facts_file, 'w') as f:
            if processor.store_raw:
                json.dump(facts, f, indent=2, sort_keys=True)
            else:
                json.dump(facts, f, separators=(',', ':'))  # Compact format
        
        result['success'] = True
        
        if verbose:
            print(f"  → {json_facts_file} (hostname: {result['hostname']}, sections: {result['sections']})")
            
    except Exception as e:
        result['error'] = str(e)
        if verbose:
            print(f"  → Error: {e}")
    
    return result


def main():
    """Main entry point for batch facts processing."""
    parser = argparse.ArgumentParser(
        description='Batch process all raw facts files to JSON format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
    TRACEROUTE_SIMULATOR_RAW_FACTS: Directory containing raw facts files
    TRACEROUTE_SIMULATOR_FACTS: Directory for output JSON files

Examples:
    # Process all raw facts files
    python3 process_all_facts.py
    
    # Process with verbose output and pretty formatting
    python3 process_all_facts.py --verbose --pretty
    
    # Process with raw data preservation
    python3 process_all_facts.py --raw
    
    # Process specific files only
    python3 process_all_facts.py --files router1_facts.txt router2_facts.txt
        """
    )
    
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('--raw', action='store_true',
                        help='Store raw/unparsed data in JSON output (increases file size)')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print JSON output with indentation')
    parser.add_argument('--files', nargs='+', metavar='FILE',
                        help='Process only specified files (filenames only, not full paths)')
    parser.add_argument('--create-dirs', action='store_true',
                        help='Create output directory if it does not exist')
    
    args = parser.parse_args()
    
    # Get directories from environment variables
    raw_facts_dir, json_facts_dir = get_facts_directories()
    
    if args.verbose:
        print(f"Raw facts directory: {raw_facts_dir}")
        print(f"JSON facts directory: {json_facts_dir}")
    
    # Check if raw facts directory exists
    if not os.path.exists(raw_facts_dir):
        print(f"Error: Raw facts directory does not exist: {raw_facts_dir}")
        print("Set TRACEROUTE_SIMULATOR_RAW_FACTS environment variable to the correct path")
        return 1
    
    # Check if JSON facts directory exists
    if not os.path.exists(json_facts_dir):
        if args.create_dirs:
            os.makedirs(json_facts_dir, exist_ok=True)
            if args.verbose:
                print(f"Created output directory: {json_facts_dir}")
        else:
            print(f"Error: JSON facts directory does not exist: {json_facts_dir}")
            print("Set TRACEROUTE_SIMULATOR_FACTS environment variable to the correct path")
            print("Or use --create-dirs to create it automatically")
            return 1
    
    # Find raw facts files to process
    raw_files = find_raw_facts_files(raw_facts_dir, args.files)
    
    if not raw_files:
        print("No raw facts files found to process")
        if args.files:
            print(f"Specified files: {args.files}")
        else:
            print(f"Searched in: {raw_facts_dir}")
        return 1
    
    if args.verbose:
        print(f"Found {len(raw_files)} raw facts files to process")
    
    # Initialize processor
    processor = FactsProcessor(verbose=args.verbose, store_raw=args.raw)
    
    # Process all files
    results = []
    success_count = 0
    error_count = 0
    
    for raw_file in raw_files:
        json_file = get_output_filename(raw_file, json_facts_dir)
        result = process_single_file(raw_file, json_file, processor, args.verbose)
        results.append(result)
        
        if result['success']:
            success_count += 1
        else:
            error_count += 1
    
    # Print summary
    print(f"\nProcessing complete:")
    print(f"  Successfully processed: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total files: {len(raw_files)}")
    
    if error_count > 0:
        print(f"\nErrors encountered:")
        for result in results:
            if not result['success']:
                print(f"  {result['raw_file']}: {result['error']}")
    
    if success_count > 0:
        print(f"\nSuccessfully processed routers:")
        for result in results:
            if result['success']:
                print(f"  {result['hostname']} ({result['sections']} sections) → {os.path.basename(result['json_file'])}")
    
    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
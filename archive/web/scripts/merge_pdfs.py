#!/usr/bin/env -S python3 -B -u
"""
Merge multiple PDF files into a single PDF document.

This script is designed to be run in the virtual environment where PyPDF2 is installed.
"""

import argparse
import json
import sys
import os
from pathlib import Path

def merge_pdfs(pdf_list, output_file):
    """
    Merge multiple PDF files into one.
    
    Args:
        pdf_list: List of PDF file paths to merge
        output_file: Path for the merged output PDF
    
    Returns:
        True if successful, False otherwise
    """
    try:
        from PyPDF2 import PdfMerger
        
        merger = PdfMerger()
        
        # Add each PDF to the merger
        for pdf_path in pdf_list:
            if os.path.exists(pdf_path):
                merger.append(pdf_path)
            else:
                print(f"Warning: PDF file not found: {pdf_path}", file=sys.stderr)
        
        # Write the merged PDF
        merger.write(output_file)
        merger.close()
        
        return True
        
    except Exception as e:
        print(f"Error merging PDFs: {str(e)}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description='Merge multiple PDF files')
    parser.add_argument('--input-list', required=True,
                       help='JSON file containing list of PDF paths to merge')
    parser.add_argument('--output', required=True,
                       help='Output PDF file path')
    parser.add_argument('--cleanup', action='store_true',
                       help='Remove individual PDFs after successful merge')
    
    args = parser.parse_args()
    
    # Read the list of PDFs to merge
    try:
        with open(args.input_list, 'r') as f:
            pdf_list = json.load(f)
    except Exception as e:
        print(f"Error reading input list: {str(e)}", file=sys.stderr)
        sys.exit(1)
    
    # Validate that we have PDFs to merge
    if not pdf_list:
        print("Error: No PDFs provided to merge", file=sys.stderr)
        sys.exit(1)
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Perform the merge
    if merge_pdfs(pdf_list, args.output):
        print(f"Successfully merged {len(pdf_list)} PDFs into {args.output}")
        
        # Clean up individual PDFs if requested
        if args.cleanup:
            for pdf_path in pdf_list:
                try:
                    if os.path.exists(pdf_path):
                        os.remove(pdf_path)
                        print(f"Removed: {pdf_path}")
                except Exception as e:
                    print(f"Warning: Could not remove {pdf_path}: {str(e)}", file=sys.stderr)
        
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
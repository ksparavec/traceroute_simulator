#!/usr/bin/env -S python3 -B -u
"""
History handler for reading XZ-compressed JSON history files.
"""

import os
import json
import lzma
from typing import List, Dict, Any


class HistoryHandler:
    """Handler for XZ-compressed JSON history files."""
    
    @staticmethod
    def read_history_file(filepath: str) -> List[Dict[str, Any]]:
        """
        Read XZ-compressed JSON history file.
        
        Args:
            filepath: Path to the history file
            
        Returns:
            List of history entries
        """
        if not os.path.exists(filepath):
            return []
        
        try:
            # Try to read as XZ-compressed file
            with lzma.open(filepath, 'rb') as f:
                data = f.read()
                history_data = json.loads(data.decode('utf-8'))
                
                # Extract history items from the cmd2 format
                if isinstance(history_data, dict) and 'history_items' in history_data:
                    return history_data['history_items']
                else:
                    return []
        except lzma.LZMAError:
            # Not XZ compressed, try plain JSON
            try:
                with open(filepath, 'r') as f:
                    history_data = json.load(f)
                    
                    # Extract history items from the cmd2 format
                    if isinstance(history_data, dict) and 'history_items' in history_data:
                        return history_data['history_items']
                    else:
                        return []
            except json.JSONDecodeError:
                # Not valid JSON either
                return []
        except Exception:
            return []
    
    @staticmethod
    def write_history_file(filepath: str, history: List[Dict[str, Any]]) -> None:
        """
        Write history to XZ-compressed JSON file.
        
        Args:
            filepath: Path to the history file
            history: List of history entries
        """
        # Create XZ-compressed JSON
        json_data = json.dumps(history, indent=2).encode('utf-8')
        with lzma.open(filepath, 'wb', preset=9) as f:
            f.write(json_data)
    
    @staticmethod
    def format_history_entry(entry: Dict[str, Any], index: int) -> str:
        """
        Format a history entry for display.
        
        Args:
            entry: History entry dict
            index: Entry index
            
        Returns:
            Formatted string
        """
        if isinstance(entry, dict):
            # Handle cmd2 history format
            statement = entry.get('statement', {})
            if isinstance(statement, dict):
                cmd = statement.get('raw', statement.get('command', ''))
            else:
                cmd = entry.get('command', entry.get('cmd', ''))
            
            # Try to get timestamp
            timestamp = entry.get('timestamp', '')
            
            if timestamp:
                return f"{index:5d}  {timestamp}  {cmd}"
            else:
                return f"{index:5d}  {cmd}"
        elif isinstance(entry, str):
            return f"{index:5d}  {entry}"
        else:
            return f"{index:5d}  {str(entry)}"
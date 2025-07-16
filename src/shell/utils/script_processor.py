# src/shell/utils/script_processor.py

import re
from typing import List, Dict, Any, Optional, Tuple
from .condition_evaluator import ConditionEvaluator

class ScriptProcessor:
    """Processes scripts with control flow structures."""
    
    def __init__(self, variable_manager, shell):
        self.variable_manager = variable_manager
        self.shell = shell
        self.condition_evaluator = ConditionEvaluator(variable_manager)
        
        # Control flow state
        self.break_flag = False
        self.continue_flag = False
        self.exit_flag = False
        self.exit_code = 0
    
    def process_script(self, lines: List[str]) -> int:
        """
        Process a script with control flow structures.
        Returns exit code (0 for success).
        """
        try:
            # Parse the script into blocks
            blocks = self._parse_blocks(lines)
            
            # Execute the blocks
            self._execute_blocks(blocks)
            
            return self.exit_code
            
        except Exception as e:
            self.shell.poutput(f"Script error: {e}")
            return 1
    
    def _parse_blocks(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parse script lines into executable blocks."""
        blocks = []
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                i += 1
                continue
            
            # Check for control structures
            if line.startswith('if '):
                block, i = self._parse_if_block(lines, i)
                blocks.append(block)
            elif line.startswith('while '):
                block, i = self._parse_while_block(lines, i)
                blocks.append(block)
            elif line.startswith('for '):
                block, i = self._parse_for_block(lines, i)
                blocks.append(block)
            else:
                # Regular command
                blocks.append({
                    'type': 'command',
                    'command': line
                })
                i += 1
        
        return blocks
    
    def _parse_if_block(self, lines: List[str], start: int) -> Tuple[Dict[str, Any], int]:
        """Parse an if/then/else/fi block."""
        i = start
        if_line = lines[i].strip()
        
        # Extract condition (everything between 'if' and 'then')
        match = re.match(r'^if\s+(.+?)\s+then\s*$', if_line)
        if not match:
            raise SyntaxError(f"Invalid if syntax at line {i+1}: {if_line}")
        
        condition = match.group(1)
        i += 1
        
        # Parse then block
        then_blocks = []
        else_blocks = []
        in_else = False
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line == 'else':
                in_else = True
                i += 1
                continue
            elif line == 'fi':
                i += 1
                break
            elif line.startswith('if '):
                # Nested if
                block, i = self._parse_if_block(lines, i)
                if in_else:
                    else_blocks.append(block)
                else:
                    then_blocks.append(block)
            elif line.startswith('while '):
                # Nested while
                block, i = self._parse_while_block(lines, i)
                if in_else:
                    else_blocks.append(block)
                else:
                    then_blocks.append(block)
            elif line.startswith('for '):
                # Nested for
                block, i = self._parse_for_block(lines, i)
                if in_else:
                    else_blocks.append(block)
                else:
                    then_blocks.append(block)
            else:
                # Regular command or empty line
                if line and not line.startswith('#'):
                    block = {'type': 'command', 'command': line}
                    if in_else:
                        else_blocks.append(block)
                    else:
                        then_blocks.append(block)
                i += 1
        
        return {
            'type': 'if',
            'condition': condition,
            'then_blocks': then_blocks,
            'else_blocks': else_blocks
        }, i
    
    def _parse_while_block(self, lines: List[str], start: int) -> Tuple[Dict[str, Any], int]:
        """Parse a while/do/done block."""
        i = start
        while_line = lines[i].strip()
        
        # Extract condition (everything between 'while' and 'do')
        match = re.match(r'^while\s+(.+?)\s+do\s*$', while_line)
        if not match:
            raise SyntaxError(f"Invalid while syntax at line {i+1}: {while_line}")
        
        condition = match.group(1)
        i += 1
        
        # Parse loop body
        body_blocks = []
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line == 'done':
                i += 1
                break
            elif line.startswith('if '):
                block, i = self._parse_if_block(lines, i)
                body_blocks.append(block)
            elif line.startswith('while '):
                block, i = self._parse_while_block(lines, i)
                body_blocks.append(block)
            elif line.startswith('for '):
                block, i = self._parse_for_block(lines, i)
                body_blocks.append(block)
            else:
                # Regular command or empty line
                if line and not line.startswith('#'):
                    body_blocks.append({'type': 'command', 'command': line})
                i += 1
        
        return {
            'type': 'while',
            'condition': condition,
            'body_blocks': body_blocks
        }, i
    
    def _parse_for_block(self, lines: List[str], start: int) -> Tuple[Dict[str, Any], int]:
        """Parse a for/in/do/done block."""
        i = start
        for_line = lines[i].strip()
        
        # Extract variable and items (for VAR in ITEMS do)
        match = re.match(r'^for\s+(\w+)\s+in\s+(.+?)\s+do\s*$', for_line)
        if not match:
            raise SyntaxError(f"Invalid for syntax at line {i+1}: {for_line}")
        
        loop_var = match.group(1)
        items_expr = match.group(2)
        i += 1
        
        # Parse loop body
        body_blocks = []
        
        while i < len(lines):
            line = lines[i].strip()
            
            if line == 'done':
                i += 1
                break
            elif line.startswith('if '):
                block, i = self._parse_if_block(lines, i)
                body_blocks.append(block)
            elif line.startswith('while '):
                block, i = self._parse_while_block(lines, i)
                body_blocks.append(block)
            elif line.startswith('for '):
                block, i = self._parse_for_block(lines, i)
                body_blocks.append(block)
            else:
                # Regular command or empty line
                if line and not line.startswith('#'):
                    body_blocks.append({'type': 'command', 'command': line})
                i += 1
        
        return {
            'type': 'for',
            'loop_var': loop_var,
            'items_expr': items_expr,
            'body_blocks': body_blocks
        }, i
    
    def _execute_blocks(self, blocks: List[Dict[str, Any]]):
        """Execute a list of blocks."""
        for block in blocks:
            if self.exit_flag:
                break
                
            if block['type'] == 'command':
                self._execute_command(block['command'])
            elif block['type'] == 'if':
                self._execute_if(block)
            elif block['type'] == 'while':
                self._execute_while(block)
            elif block['type'] == 'for':
                self._execute_for(block)
            
            # Handle continue flag (only affects loops)
            if self.continue_flag:
                # This will be handled by the loop
                break
    
    def _execute_command(self, command: str):
        """Execute a single command."""
        if self.exit_flag:
            return
        
        # Handle special commands
        if command == 'break':
            self.break_flag = True
            return
        elif command == 'continue':
            self.continue_flag = True
            return
        elif command.startswith('exit'):
            self.exit_flag = True
            # Check for exit code
            parts = command.split()
            if len(parts) > 1:
                try:
                    self.exit_code = int(parts[1])
                except ValueError:
                    self.exit_code = 1
            return
        
        # Execute normal command through the shell
        # First substitute variables
        command = self.variable_manager.substitute_variables(command)
        # Then execute (only if not already handled by flags)
        if not (self.break_flag or self.continue_flag or self.exit_flag):
            self.shell.onecmd(command)
    
    def _execute_if(self, block: Dict[str, Any]):
        """Execute an if block."""
        if self.exit_flag:
            return
        
        # Evaluate condition
        try:
            condition_met = self.condition_evaluator.evaluate(block['condition'])
        except Exception as e:
            self.shell.poutput(f"Error evaluating condition: {e}")
            return
        
        # Execute appropriate branch
        if condition_met:
            self._execute_blocks(block['then_blocks'])
        else:
            self._execute_blocks(block['else_blocks'])
    
    def _execute_while(self, block: Dict[str, Any]):
        """Execute a while loop."""
        while not self.exit_flag:
            # Evaluate condition
            try:
                condition_met = self.condition_evaluator.evaluate(block['condition'])
            except Exception as e:
                self.shell.poutput(f"Error evaluating condition: {e}")
                break
            
            if not condition_met:
                break
            
            # Reset continue flag before each iteration
            self.continue_flag = False
            
            # Execute loop body
            self._execute_blocks(block['body_blocks'])
            
            # Check for break
            if self.break_flag:
                self.break_flag = False
                break
    
    def _execute_for(self, block: Dict[str, Any]):
        """Execute a for loop."""
        if self.exit_flag:
            return
        
        # Get the items to iterate over
        items_expr = block['items_expr']
        
        # Substitute variables in the items expression
        items_expr = self.variable_manager.substitute_variables(items_expr)
        
        # Parse items (space-separated)
        # Handle quoted strings properly
        items = self._parse_items(items_expr)
        
        # Save original variable value (if exists)
        loop_var = block['loop_var']
        original_value = self.variable_manager.variables.get(loop_var)
        
        # Iterate over items
        for item in items:
            if self.exit_flag:
                break
            
            # Set loop variable
            self.variable_manager.set_variable(loop_var, item)
            
            # Reset continue flag before each iteration
            self.continue_flag = False
            
            # Execute loop body
            self._execute_blocks(block['body_blocks'])
            
            # Check for break
            if self.break_flag:
                self.break_flag = False
                break
        
        # Restore original variable value
        if original_value is not None:
            self.variable_manager.set_variable(loop_var, original_value)
        elif loop_var in self.variable_manager.variables:
            del self.variable_manager.variables[loop_var]
    
    def _parse_items(self, items_expr: str) -> List[str]:
        """Parse space-separated items, respecting quotes and JSON arrays."""
        # First check if it's a JSON array
        items_expr = items_expr.strip()
        if items_expr.startswith('[') and items_expr.endswith(']'):
            try:
                import json
                # Parse as JSON array
                items = json.loads(items_expr)
                # Convert all items to strings
                return [str(item) for item in items]
            except json.JSONDecodeError:
                # Fall back to regular parsing
                pass
        
        # Regular parsing for space-separated items
        items = []
        current = []
        in_quotes = False
        quote_char = None
        
        for char in items_expr:
            if not in_quotes:
                if char in '"\'':
                    in_quotes = True
                    quote_char = char
                elif char == ' ':
                    if current:
                        items.append(''.join(current))
                        current = []
                else:
                    current.append(char)
            else:
                if char == quote_char:
                    in_quotes = False
                    quote_char = None
                else:
                    current.append(char)
        
        # Add last item
        if current:
            items.append(''.join(current))
        
        return items
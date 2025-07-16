# src/shell/utils/variable_manager.py

import json
import re
import subprocess
from typing import Any, Dict, Optional

class VariableManager:
    """Manages shell variables, substitution, and command execution for variables."""

    def __init__(self, shell_instance):
        self.shell = shell_instance
        self.variables: Dict[str, Any] = {}

    def set_variable(self, key: str, value: Any):
        """Sets a variable, parsing JSON strings into dictionaries if possible."""
        if isinstance(value, str):
            try:
                # Attempt to parse the string as JSON
                parsed_value = json.loads(value)
                self.variables[key] = parsed_value
                # Debug message - only shown with -vvv (not available in shell yet)
            except json.JSONDecodeError:
                # If not JSON, store as a plain string
                self.variables[key] = value.strip()
        else:
            self.variables[key] = value

    def get_variable(self, name: str) -> Optional[Any]:
        """
        Retrieves a variable's value, supporting nested access for dictionaries and lists.
        e.g., "mydict.key1[0]['key-2']"
        """
        if not name:
            return None

        # Extract the base variable name
        base_var_match = re.match(r'([a-zA-Z_][a-zA-Z0-9_]*)', name)
        if not base_var_match:
            return None
        
        base_var_name = base_var_match.group(1)
        if base_var_name not in self.variables:
            return None
        
        value = self.variables[base_var_name]
        
        # Extract the chain of accessors
        accessors_str = name[base_var_match.end():]
        # This regex finds all .key, .method(), or [key] style accessors
        accessor_pattern = re.compile(r'\.([a-zA-Z_][a-zA-Z0-9_]*)(\(\))?|\[([^\]]+)\]')
        accessor_matches = accessor_pattern.findall(accessors_str)

        for dot_key, method_parens, bracket_key in accessor_matches:
            if value is None:
                return None
            
            # Check if it's a known method (with or without parentheses)
            if dot_key in ['keys', 'values']:
                # Handle method calls on dictionaries
                if isinstance(value, dict) and dot_key == 'keys':
                    value = list(value.keys())
                    continue
                elif isinstance(value, dict) and dot_key == 'values':
                    value = list(value.values())
                    continue
                else:
                    return None  # Method not applicable to this type
            
            key = dot_key or bracket_key
            
            # First, try list access if the key is an integer
            if isinstance(value, list):
                try:
                    idx = int(key)
                    if -len(value) <= idx < len(value):
                        value = value[idx]
                        continue
                    else:
                        return None # Index out of bounds
                except (ValueError, IndexError):
                    # If it's not a valid integer index, it can't be a list access
                    return None

            # Second, try dictionary access
            elif isinstance(value, dict):
                # If the key from brackets is quoted, unquote it
                if bracket_key and ((key.startswith("'") and key.endswith("'")) or \
                   (key.startswith('"') and key.endswith('"'))):
                    key = key[1:-1]
                
                value = value.get(key)
            
            # If it's neither a list nor a dict, we can't access further
            else:
                return None
            
        return value

    def substitute_variables(self, command: str) -> str:
        """
        Performs variable substitution on a command string.
        Supports $VAR, ${VAR}, and nested access like $mydict.key[0].
        Also supports one level of variable substitution within brackets.
        """
        # First, find complex variable references with brackets that may contain other variables
        # Match $VAR[...] where ... may contain other $VARS
        complex_pattern = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_]*)((?:\[[^\]]*\])+)')
        
        def replace_complex(match):
            base_var = match.group(1)
            bracket_part = match.group(2)
            
            # Check if bracket part contains any variables
            if '$' not in bracket_part:
                # No variables to substitute, process normally
                return match.group(0)
            
            # Replace any $VAR references within the bracket part
            simple_var_pattern = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_]*)')
            
            def replace_simple_var(var_match):
                var_name = var_match.group(1)
                var_value = self.variables.get(var_name)
                if var_value is None:
                    return var_match.group(0)
                # For use in bracket notation, wrap strings in quotes
                if isinstance(var_value, str):
                    return f'"{var_value}"'
                return str(var_value)
            
            # Substitute variables within brackets
            substituted_brackets = simple_var_pattern.sub(replace_simple_var, bracket_part)
            
            # Now evaluate the complete expression
            full_expression = base_var + substituted_brackets
            value = self.get_variable(full_expression)
            
            if value is None:
                return match.group(0)
            
            if isinstance(value, (dict, list)):
                return json.dumps(value, separators=(',', ':'))
            
            return str(value)
        
        # First pass: handle complex expressions with variables in brackets
        command = complex_pattern.sub(replace_complex, command)
        
        # Second pass: handle remaining simple variables
        simple_pattern = re.compile(r'\$({)?([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*(?:\(\))?|\[[^\]]+\])*)(?(1)})')
        
        def replace_simple(match):
            var_name = match.group(2)
            value = self.get_variable(var_name)

            if value is None:
                return match.group(0)
            
            if isinstance(value, (dict, list)):
                # Use json.dumps with separators to ensure no spaces after colons/commas
                return json.dumps(value, separators=(',', ':'))
            
            return str(value)

        return simple_pattern.sub(replace_simple, command)

    def process_command_for_assignment(self, command: str) -> bool:
        """
        Checks if a command is a variable assignment and processes it.
        Returns True if it was an assignment, False otherwise.
        """
        assignment_pattern = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)', command, re.DOTALL)
        if not assignment_pattern:
            return False

        var_name = assignment_pattern.group(1)
        value_str = assignment_pattern.group(2).strip()

        # Case 1: Command substitution, e.g., VAR=$(command)
        if value_str.startswith('$(') and value_str.endswith(')'):
            sub_expr = value_str[2:-1]
            
            # Check if it's arithmetic expression $((...))
            if sub_expr.startswith('(') and sub_expr.endswith(')'):
                # Arithmetic expression
                arith_expr = sub_expr[1:-1]
                try:
                    # Substitute variables in the expression
                    arith_expr = self.substitute_variables(arith_expr)
                    # Evaluate the expression
                    result = eval(arith_expr, {"__builtins__": {}}, {})
                    self.set_variable(var_name, str(result))
                except Exception as e:
                    from colorama import Fore, Style
                    self.shell.poutput(f"{Fore.RED}Error evaluating arithmetic expression: {e}{Style.RESET_ALL}")
                    self.set_variable(var_name, "0")
            else:
                # Command substitution
                sub_command = sub_expr
                # Execute the command in the system shell to support external commands
                try:
                    from colorama import Fore, Style
                    result = subprocess.run(sub_command, shell=True, capture_output=True, text=True)
                    if result.returncode == 0:
                        self.set_variable(var_name, result.stdout.strip())
                    else:
                        self.shell.poutput(f"{Fore.RED}Error during command substitution:\n{result.stderr.strip()}{Style.RESET_ALL}")
                        self.set_variable(var_name, "") # Set to empty on failure
                except subprocess.SubprocessError as e:
                    self.shell.poutput(f"{Fore.RED}Subprocess error during command substitution: {e}{Style.RESET_ALL}")
                    self.set_variable(var_name, "")
                except OSError as e:
                    self.shell.poutput(f"{Fore.RED}OS error during command substitution: {e}{Style.RESET_ALL}")
                    self.set_variable(var_name, "")
                except ValueError as e:
                    self.shell.poutput(f"{Fore.RED}Invalid arguments during command substitution: {e}{Style.RESET_ALL}")
                    self.set_variable(var_name, "")
        
        # Case 2: Regular assignment with potential substitution on the right side
        else:
            # Remove surrounding quotes if present (single or double)
            if ((value_str.startswith("'") and value_str.endswith("'")) or 
                (value_str.startswith('"') and value_str.endswith('"'))) and len(value_str) >= 2:
                value_str = value_str[1:-1]
            
            # First, perform any variable substitutions on the right-hand side
            substituted_value = self.substitute_variables(value_str)
            
            # Now, set the variable. If the substituted value is a JSON string,
            # set_variable will parse it into a dictionary/list.
            self.set_variable(var_name, substituted_value)

        return True

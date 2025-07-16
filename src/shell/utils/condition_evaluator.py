# src/shell/utils/condition_evaluator.py

import re
from typing import Any, Optional, Tuple

class ConditionEvaluator:
    """Evaluates conditions for control flow statements."""
    
    def __init__(self, variable_manager):
        self.variable_manager = variable_manager
        
        # Comparison operators
        self.operators = {
            '==': self._eq,
            '!=': self._ne,
            '>': self._gt,
            '>=': self._ge,
            '<': self._lt,
            '<=': self._le,
        }
    
    def evaluate(self, condition: str) -> bool:
        """
        Evaluate a condition like '$VAR == "value"' or '$COUNT > 5'.
        Returns True if condition is met, False otherwise.
        """
        # First, substitute any variables in the condition
        condition = self.variable_manager.substitute_variables(condition)
        
        # Parse the condition to extract left operand, operator, and right operand
        parsed = self._parse_condition(condition)
        if not parsed:
            raise ValueError(f"Invalid condition: {condition}")
        
        left, operator, right = parsed
        
        # Get the comparison function
        if operator not in self.operators:
            raise ValueError(f"Unknown operator: {operator}")
        
        compare_func = self.operators[operator]
        
        # Evaluate and return result
        try:
            return compare_func(left, right)
        except Exception as e:
            raise ValueError(f"Error evaluating condition '{condition}': {e}")
    
    def _parse_condition(self, condition: str) -> Optional[Tuple[str, str, str]]:
        """Parse condition into (left, operator, right) tuple."""
        # Pattern to match: value operator value
        # Handles quoted strings, numbers, and unquoted strings
        pattern = r'^\s*(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$'
        
        match = re.match(pattern, condition)
        if not match:
            return None
        
        left = match.group(1).strip()
        operator = match.group(2)
        right = match.group(3).strip()
        
        # Remove quotes if present
        left = self._unquote(left)
        right = self._unquote(right)
        
        return (left, operator, right)
    
    def _unquote(self, value: str) -> str:
        """Remove surrounding quotes if present."""
        if len(value) >= 2:
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                return value[1:-1]
        return value
    
    def _to_number(self, value: str) -> Optional[float]:
        """Try to convert string to number."""
        try:
            # Try integer first
            if '.' not in value:
                return int(value)
            # Then float
            return float(value)
        except ValueError:
            return None
    
    def _compare_values(self, left: str, right: str, numeric_op, string_op):
        """Compare two values, automatically detecting type."""
        # Try numeric comparison first
        left_num = self._to_number(left)
        right_num = self._to_number(right)
        
        if left_num is not None and right_num is not None:
            # Both are numbers
            return numeric_op(left_num, right_num)
        else:
            # String comparison
            return string_op(left, right)
    
    # Comparison operators
    def _eq(self, left: str, right: str) -> bool:
        """Equal comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a == b,
                                   lambda a, b: a == b)
    
    def _ne(self, left: str, right: str) -> bool:
        """Not equal comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a != b,
                                   lambda a, b: a != b)
    
    def _gt(self, left: str, right: str) -> bool:
        """Greater than comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a > b,
                                   lambda a, b: a > b)
    
    def _ge(self, left: str, right: str) -> bool:
        """Greater than or equal comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a >= b,
                                   lambda a, b: a >= b)
    
    def _lt(self, left: str, right: str) -> bool:
        """Less than comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a < b,
                                   lambda a, b: a < b)
    
    def _le(self, left: str, right: str) -> bool:
        """Less than or equal comparison."""
        return self._compare_values(left, right,
                                   lambda a, b: a <= b,
                                   lambda a, b: a <= b)
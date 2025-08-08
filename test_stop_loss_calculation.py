#!/usr/bin/env python3
"""
Test script to verify the stop loss calculation logic.
This script tests the percentage-based stop loss calculation without requiring a live connection.
"""

def calculate_percentage_stop_loss(current_price: float, position_type: str, percentage: float) -> float:
    """
    Calculate a percentage-based stop loss price from the current market price.
    
    Args:
        current_price: Current market price
        position_type: The position type ('LONG' or 'SHORT')
        percentage: The percentage for stop loss calculation (e.g., 2.0 for 2%)
        
    Returns:
        The calculated stop loss price
    """
    # Validate percentage input
    if percentage <= 0 or percentage > 50:
        raise ValueError(f"Invalid stop loss percentage: {percentage}%. Must be between 0.1 and 50.")
    
    # Calculate percentage-based stop loss from current price
    if position_type.upper() == 'LONG':
        stop_loss_price = current_price * (1 - percentage / 100)  # percentage below current price
        print(f"LONG position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
    elif position_type.upper() == 'SHORT':
        stop_loss_price = current_price * (1 + percentage / 100)  # percentage above current price
        print(f"SHORT position: Calculated {percentage}% stop loss. Current: {current_price}, SL: {stop_loss_price}")
    else:
        raise ValueError(f"Unknown position type: {position_type}")
    
    return stop_loss_price

def test_stop_loss_calculations():
    """Test various stop loss calculation scenarios."""
    print("=== Testing Stop Loss Calculations ===\n")
    
    # Test cases
    test_cases = [
        {"current_price": 50000, "position_type": "LONG", "percentage": 2.0, "expected_description": "BTC at $50k, LONG, 2% SL"},
        {"current_price": 50000, "position_type": "SHORT", "percentage": 2.0, "expected_description": "BTC at $50k, SHORT, 2% SL"},
        {"current_price": 0.5, "position_type": "LONG", "percentage": 5.0, "expected_description": "DOGE at $0.5, LONG, 5% SL"},
        {"current_price": 0.5, "position_type": "SHORT", "percentage": 5.0, "expected_description": "DOGE at $0.5, SHORT, 5% SL"},
        {"current_price": 3000, "position_type": "LONG", "percentage": 1.5, "expected_description": "ETH at $3k, LONG, 1.5% SL"},
        {"current_price": 3000, "position_type": "SHORT", "percentage": 1.5, "expected_description": "ETH at $3k, SHORT, 1.5% SL"},
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['expected_description']}")
        try:
            result = calculate_percentage_stop_loss(
                test_case['current_price'],
                test_case['position_type'],
                test_case['percentage']
            )
            
            # Verify the calculation is correct
            if test_case['position_type'] == 'LONG':
                expected = test_case['current_price'] * (1 - test_case['percentage'] / 100)
            else:  # SHORT
                expected = test_case['current_price'] * (1 + test_case['percentage'] / 100)
            
            assert abs(result - expected) < 0.000001, f"Calculation mismatch: {result} vs {expected}"
            print(f"✓ PASS: Stop loss calculated correctly\n")
            
        except Exception as e:
            print(f"✗ FAIL: {e}\n")
    
    # Test error cases
    print("=== Testing Error Cases ===\n")
    
    error_cases = [
        {"current_price": 50000, "position_type": "LONG", "percentage": 0, "expected_error": "Invalid percentage"},
        {"current_price": 50000, "position_type": "LONG", "percentage": 60, "expected_error": "Invalid percentage"},
        {"current_price": 50000, "position_type": "SPOT", "percentage": 2.0, "expected_error": "Unknown position type"},
    ]
    
    for i, test_case in enumerate(error_cases, 1):
        print(f"Error Test {i}: {test_case['expected_error']}")
        try:
            result = calculate_percentage_stop_loss(
                test_case['current_price'],
                test_case['position_type'],
                test_case['percentage']
            )
            print(f"✗ FAIL: Expected error but got result: {result}\n")
        except Exception as e:
            print(f"✓ PASS: Correctly caught error: {e}\n")
    
    print("=== All Tests Completed ===")

if __name__ == "__main__":
    test_stop_loss_calculations() 
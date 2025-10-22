#!/usr/bin/env python3
"""
Run Status Fix Script

Simple script to run the status inconsistency fix.
"""

import os
import sys
import subprocess

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def main():
    """Run the status fix script."""
    script_path = os.path.join(os.path.dirname(__file__), 'fix_status_inconsistencies.py')

    print("Running status inconsistency fix...")
    print("=" * 50)

    try:
        result = subprocess.run([sys.executable, script_path], check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Warnings/Errors:")
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error running status fix: {e}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

    print("=" * 50)
    print("Status fix completed!")

if __name__ == "__main__":
    main()

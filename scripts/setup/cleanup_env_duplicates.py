#!/usr/bin/env python3
"""
.env File Cleanup Utility

This script helps clean up duplicate environment variables in your .env file
by commenting out all but the last occurrence of each variable.
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

def backup_env_file(env_file_path):
    """Create a backup of the .env file before modification."""
    backup_path = f"{env_file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(env_file_path, backup_path)
    print(f"📄 Backup created: {backup_path}")
    return backup_path

def analyze_env_file(env_file_path):
    """Analyze .env file for duplicate variables."""
    with open(env_file_path, 'r') as f:
        lines = f.readlines()

    # Track variables and their line numbers
    variables = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            continue

        # Look for variable assignments
        if '=' in stripped:
            var_name = stripped.split('=')[0].strip()
            if var_name not in variables:
                variables[var_name] = []
            variables[var_name].append(i)

    # Find duplicates
    duplicates = {var: line_nums for var, line_nums in variables.items() if len(line_nums) > 1}

    return lines, duplicates

def cleanup_env_file(env_file_path, dry_run=True):
    """Clean up duplicate environment variables."""
    print(f"🔍 Analyzing: {env_file_path}")

    lines, duplicates = analyze_env_file(env_file_path)

    if not duplicates:
        print("✅ No duplicate variables found!")
        return

    print(f"\n📋 Found {len(duplicates)} variables with duplicates:")
    for var, line_nums in duplicates.items():
        print(f"   {var}: lines {', '.join(str(n+1) for n in line_nums)}")

    if dry_run:
        print(f"\n🔍 DRY RUN - Showing what would be changed:")
        for var, line_nums in duplicates.items():
            # Keep the last occurrence, comment out the rest
            for line_num in line_nums[:-1]:  # All but the last
                line = lines[line_num].rstrip()
                print(f"   Line {line_num+1}: WOULD COMMENT -> # {line}")

        print(f"\n💡 To apply changes, run with --apply flag")
        return

    # Apply changes
    print(f"\n🔧 Applying changes...")

    # Create backup first
    backup_path = backup_env_file(env_file_path)

    # Comment out duplicates (keep last occurrence)
    changes_made = 0
    for var, line_nums in duplicates.items():
        for line_num in line_nums[:-1]:  # All but the last
            original_line = lines[line_num]
            if not original_line.strip().startswith('#'):
                lines[line_num] = f"# {original_line}"
                changes_made += 1
                print(f"   ✅ Commented line {line_num+1}: {var}")

    # Write back to file
    with open(env_file_path, 'w') as f:
        f.writelines(lines)

    print(f"\n🎉 Cleanup complete!")
    print(f"   📝 Changes made: {changes_made}")
    print(f"   💾 Original file backed up to: {backup_path}")

def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description='Clean up duplicate environment variables in .env file')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry run)')
    parser.add_argument('--env-file', default='.env', help='Path to .env file (default: .env)')

    args = parser.parse_args()

    env_file_path = Path(args.env_file)

    print("="*70)
    print("              .ENV FILE CLEANUP UTILITY")
    print("="*70)

    if not env_file_path.exists():
        print(f"❌ .env file not found: {env_file_path}")
        print(f"📁 Current directory: {os.getcwd()}")
        sys.exit(1)

    print(f"📁 Working directory: {os.getcwd()}")
    print(f"📄 Target file: {env_file_path.absolute()}")

    if args.apply:
        print("⚠️  APPLY MODE - Changes will be made to your .env file!")
        response = input("Continue? [y/N]: ")
        if response.lower() != 'y':
            print("❌ Operation cancelled")
            sys.exit(0)

    try:
        cleanup_env_file(env_file_path, dry_run=not args.apply)

        if not args.apply:
            print(f"\n🔄 To apply these changes, run:")
            print(f"   python {sys.argv[0]} --apply")
        else:
            print(f"\n🎯 Next steps:")
            print(f"   1. Review the changes in your .env file")
            print(f"   2. Run: python scripts/verify_startup_env.py")
            print(f"   3. Restart your application")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    print("="*70)

if __name__ == "__main__":
    main()
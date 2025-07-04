#!/usr/bin/env python3
"""
Startup Environment Verification Script

This script helps diagnose environment variable loading issues.
Run this BEFORE starting your main application to verify that
your .env file changes are being loaded correctly.
"""

import os
import sys
import time
from pathlib import Path

def check_env_file():
    """Check .env file existence and content."""
    print("="*70)
    print("                .ENV FILE ANALYSIS")
    print("="*70)

    # Look for .env file in current directory and parent directories
    current_dir = Path.cwd()
    env_paths_to_check = [
        current_dir / '.env',
        current_dir.parent / '.env',
        Path(os.path.expanduser('~')) / '.env',
    ]

    found_env_files = []
    for env_path in env_paths_to_check:
        if env_path.exists():
            found_env_files.append(env_path)
            print(f"✅ Found .env file: {env_path}")
            mod_time = env_path.stat().st_mtime
            print(f"   📅 Last modified: {time.ctime(mod_time)}")
            print(f"   📏 File size: {env_path.stat().st_size} bytes")
        else:
            print(f"❌ No .env file at: {env_path}")

    if not found_env_files:
        print("\n⚠️  WARNING: No .env files found!")
        return None

    # Analyze the first .env file found
    env_file = found_env_files[0]
    print(f"\n🔍 Analyzing: {env_file}")

    try:
        with open(env_file, 'r') as f:
            lines = f.readlines()

        print(f"📄 Total lines in .env file: {len(lines)}")

        # Find all Binance-related lines
        binance_lines = []
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if 'BINANCE_API_KEY' in line or 'BINANCE_API_SECRET' in line:
                status = "ACTIVE" if not line.startswith('#') else "COMMENTED"
                binance_lines.append((i, line, status))

        print(f"\n🔑 Found {len(binance_lines)} Binance credential lines:")
        for line_num, line, status in binance_lines:
            # Mask sensitive parts
            if 'BINANCE_API_KEY' in line:
                parts = line.split('=', 1)
                if len(parts) == 2 and len(parts[1]) > 10:
                    masked_line = f"{parts[0]}={parts[1][:8]}...{parts[1][-4:]}"
                else:
                    masked_line = line
            else:
                masked_line = line[:30] + "..." if len(line) > 30 else line

            print(f"   Line {line_num:2d}: [{status:>9}] {masked_line}")

        # Count active vs commented
        active_keys = sum(1 for _, line, status in binance_lines if status == "ACTIVE" and 'API_KEY' in line)
        active_secrets = sum(1 for _, line, status in binance_lines if status == "ACTIVE" and 'API_SECRET' in line)

        print(f"\n📊 Summary:")
        print(f"   Active BINANCE_API_KEY lines: {active_keys}")
        print(f"   Active BINANCE_API_SECRET lines: {active_secrets}")

        if active_keys > 1 or active_secrets > 1:
            print("   ⚠️  WARNING: Multiple active credentials detected!")
        elif active_keys == 1 and active_secrets == 1:
            print("   ✅ Exactly one set of active credentials found.")
        else:
            print("   ❌ Missing or incomplete credentials.")

        return env_file

    except Exception as e:
        print(f"❌ Error reading .env file: {e}")
        return None

def test_env_loading():
    """Test environment variable loading without importing application modules."""
    print("\n" + "="*70)
    print("              ENVIRONMENT LOADING TEST")
    print("="*70)

    # Clear any existing environment variables to test fresh loading
    original_key = os.environ.get('BINANCE_API_KEY')
    original_secret = os.environ.get('BINANCE_API_SECRET')

    print(f"🔍 Current system environment:")
    print(f"   BINANCE_API_KEY: {'SET' if original_key else 'NOT SET'}")
    print(f"   BINANCE_API_SECRET: {'SET' if original_secret else 'NOT SET'}")

    # Test python-dotenv loading
    try:
        from dotenv import load_dotenv
        print(f"\n✅ python-dotenv is available")

        # Load with override
        load_result = load_dotenv(override=True)
        print(f"🔄 load_dotenv(override=True) result: {load_result}")

        # Check what was loaded
        new_key = os.getenv('BINANCE_API_KEY')
        new_secret = os.getenv('BINANCE_API_SECRET')
        new_testnet = os.getenv('BINANCE_TESTNET', 'True').lower() == 'true'

        print(f"\n📊 Loaded values:")
        print(f"   BINANCE_API_KEY: {new_key[:15]}...{new_key[-10:] if new_key and len(new_key) > 25 else 'NOT_SET'}")
        print(f"   BINANCE_API_SECRET: {new_secret[:15]}...{new_secret[-10:] if new_secret and len(new_secret) > 25 else 'NOT_SET'}")
        print(f"   BINANCE_TESTNET: {new_testnet}")

        if new_key and new_secret:
            print("   ✅ Credentials successfully loaded from .env file")
            return True
        else:
            print("   ❌ Failed to load credentials from .env file")
            return False

    except ImportError:
        print("❌ python-dotenv is not installed!")
        print("   Install it with: pip install python-dotenv")
        return False
    except Exception as e:
        print(f"❌ Error loading environment: {e}")
        return False

def main():
    """Main diagnostic function."""
    print("🚀 Starting Environment Variable Diagnostic")
    print(f"📁 Current working directory: {os.getcwd()}")
    print(f"🐍 Python version: {sys.version}")
    print()

    # Step 1: Check .env file
    env_file = check_env_file()

    # Step 2: Test environment loading
    load_success = test_env_loading()

    # Step 3: Final recommendations
    print("\n" + "="*70)
    print("                   RECOMMENDATIONS")
    print("="*70)

    if env_file and load_success:
        print("✅ Environment setup looks good!")
        print("   Your application should load the correct credentials on startup.")
    else:
        print("❌ Issues detected:")
        if not env_file:
            print("   1. Create a .env file in your project root directory")
        if not load_success:
            print("   2. Ensure python-dotenv is installed: pip install python-dotenv")
            print("   3. Check that your .env file has the correct format:")
            print("      BINANCE_API_KEY=your_actual_key_here")
            print("      BINANCE_API_SECRET=your_actual_secret_here")

    print(f"\n🎯 Next steps:")
    print(f"   1. Make sure only ONE set of BINANCE_API_KEY/SECRET is uncommented")
    print(f"   2. Restart your application/server")
    print(f"   3. Check the startup logs for credential verification")

    print("="*70)

if __name__ == "__main__":
    main()
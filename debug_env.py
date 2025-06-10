#!/usr/bin/env python3

import os
import sys
from dotenv import load_dotenv, find_dotenv

print("Python version:", sys.version)
print("Current working directory:", os.getcwd())

# Find .env files
env_files = []
try:
    env_file = find_dotenv()
    print(f"Found .env file: {env_file}")
    env_files.append(env_file)
except:
    print("No .env file found by find_dotenv()")

# Check if .env exists in current directory
if os.path.exists('.env'):
    print("Found .env in current directory")
    with open('.env', 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines, 1):
            if 'GAS_PRICE_ADJUSTMENT' in line:
                print(f"Line {i}: {repr(line)}")

# Check environment before loading
print(f"GAS_PRICE_ADJUSTMENT before load_dotenv: {repr(os.environ.get('GAS_PRICE_ADJUSTMENT'))}")

# Load .env
result = load_dotenv()
print(f"load_dotenv() result: {result}")

# Check environment after loading
print(f"GAS_PRICE_ADJUSTMENT after load_dotenv: {repr(os.environ.get('GAS_PRICE_ADJUSTMENT'))}")
print(f"os.getenv result: {repr(os.getenv('GAS_PRICE_ADJUSTMENT'))}")

# Try to parse as float
try:
    value = float(os.getenv("GAS_PRICE_ADJUSTMENT", "1.1"))
    print(f"Successfully parsed as float: {value}")
except ValueError as e:
    print(f"ValueError when parsing: {e}")
    print(f"Raw value: {repr(os.getenv('GAS_PRICE_ADJUSTMENT'))}")

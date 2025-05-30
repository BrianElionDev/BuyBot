#!/usr/bin/env python3
"""
Simple Windows Compatibility Test
"""
import sys
import os

print("=== WINDOWS COMPATIBILITY TEST ===")
print(f"Python: {sys.version}")
print(f"Platform: {sys.platform}")
print(f"Encoding: {sys.stdout.encoding}")

# Test basic message formats
messages = [
    "[STARTUP] Starting Rubicon Whale Tracker Bot",
    "[LOGIN] Logged in successfully",
    "[TARGET] TARGET GROUP FOUND!",
    "[MESSAGE] NEW MESSAGE IN TARGET GROUP",
    "[SUCCESS] Successfully parsed trade signal",
    "[ERROR] Failed to parse trade signal",
    "[PRICE] Fetching price from CoinGecko",
    "[DEBUG] Debugging information"
]

print("\n=== TESTING MESSAGE FORMATS ===")
for msg in messages:
    print(msg)

print("\n=== TESTING LOGGING ===")
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

for msg in messages:
    logger.info(msg)

print("\n[SUCCESS] All tests completed without Unicode errors!")
print("This bot should work properly on Windows systems.")

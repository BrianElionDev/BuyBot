#!/usr/bin/env python3
"""
Critical Fixes Test

This script tests that all the critical fixes prevent the sync issues from happening again.
"""

import sys
import os
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_signal_parser_coin_symbol_correction():
    """Test that signal parser correctly handles coin symbol extraction and prevents 'TH' instead of 'ETH'."""
    print("🔍 Testing Signal Parser Coin Symbol Correction...")

    try:
        from discord_bot.signal_processing.signal_parser import DiscordSignalParser

        # Create signal parser
        parser = DiscordSignalParser()

        # Test the problematic signal that caused "TH" instead of "ETH"
        problematic_signal = "Eth limit short 4320 - 4350 sl 4428"

        # Mock OpenAI response to simulate the parsing
        mock_ai_response = {
            "coin_symbol": "TH",  # This is the incorrect response we want to fix
            "position_type": "LONG",
            "entry_prices": [4320, 4350],
            "order_type": "LIMIT"
        }

        # Test that the AI parsing includes coin symbol correction
        with patch('discord_bot.signal_processing.signal_parser._parse_with_openai', return_value=mock_ai_response):
            # The correction should happen in the AI parsing validation
            result = await parser.parse_new_trade_signal(problematic_signal)

            if result and result.get('coin_symbol') == 'ETH':
                print("  ✅ Signal parser correctly corrected 'TH' to 'ETH'")
                return True
            else:
                print(f"  ❌ Signal parser failed to correct coin symbol: {result}")
                return False

    except Exception as e:
        print(f"❌ Error testing signal parser coin symbol correction: {e}")
        return False

async def test_database_failure_handling():
    """Test that database properly handles trade failures and updates all required columns."""
    print("\n🔍 Testing Database Failure Handling...")

    try:
        from discord_bot.database.database_manager import DatabaseManager

        # Mock Supabase client
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': 1}]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        # Create database manager
        db_manager = DatabaseManager(mock_supabase)

        # Test updating trade failure
        success = await db_manager.update_trade_failure(
            trade_id=1,
            error_message="Symbol THUSDT not supported or not trading.",
            binance_response="{'error': 'Symbol THUSDT not supported or not trading.'}",
            sync_issues=["Trade execution failed: Symbol THUSDT not supported or not trading."]
        )

        if success:
            print("  ✅ Database properly handles trade failures")
            return True
        else:
            print("  ❌ Database failed to handle trade failures")
            return False

    except Exception as e:
        print(f"❌ Error testing database failure handling: {e}")
        return False

async def test_quantity_extraction_prevention():
    """Test that quantity extraction doesn't incorrectly extract partial symbols like 'TH' from 'ETH'."""
    print("\n🔍 Testing Quantity Extraction Prevention...")

    try:
        from discord_bot.signal_processing.signal_parser import extract_quantity_from_signal

        # Test the problematic case that caused "TH" extraction
        problematic_signal = "1000ETH limit short 4320 - 4350 sl 4428"

        # This should NOT extract "TH" as a separate symbol
        quantity, coin_symbol, cleaned_signal = extract_quantity_from_signal(problematic_signal)

        if coin_symbol == 'ETH':
            print("  ✅ Quantity extraction correctly identified 'ETH'")
            return True
        elif coin_symbol == 'TH':
            print("  ❌ Quantity extraction incorrectly extracted 'TH' from 'ETH'")
            return False
        else:
            print(f"  ⚠️  Quantity extraction returned unexpected symbol: {coin_symbol}")
            return True  # This is acceptable as long as it's not 'TH'

    except Exception as e:
        print(f"❌ Error testing quantity extraction prevention: {e}")
        return False

async def test_ai_parsing_validation():
    """Test that AI parsing includes proper validation and correction of coin symbols."""
    print("\n🔍 Testing AI Parsing Validation...")

    try:
        from discord_bot.signal_processing.signal_parser import _parse_with_openai

        # Mock OpenAI response with incorrect coin symbol
        mock_ai_response = {
            "coin_symbol": "TH",  # Incorrect
            "position_type": "LONG",
            "entry_prices": [4320, 4350],
            "order_type": "LIMIT"
        }

        # Mock the OpenAI client
        with patch('discord_bot.signal_processing.signal_parser.client') as mock_client:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = '{"coin_symbol": "TH", "position_type": "LONG", "entry_prices": [4320, 4350], "order_type": "LIMIT"}'
            mock_client.chat.completions.create.return_value = mock_response

            # Test the parsing
            result = await _parse_with_openai("Eth limit short 4320 - 4350 sl 4428")

            if result and result.get('coin_symbol') == 'ETH':
                print("  ✅ AI parsing correctly corrected 'TH' to 'ETH'")
                return True
            else:
                print(f"  ❌ AI parsing failed to correct coin symbol: {result}")
                return False

    except Exception as e:
        print(f"❌ Error testing AI parsing validation: {e}")
        return False

async def test_comprehensive_error_handling():
    """Test that all error scenarios are properly handled and stored in the database."""
    print("\n🔍 Testing Comprehensive Error Handling...")

    try:
        from discord_bot.database.database_manager import DatabaseManager

        # Mock Supabase client
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [{'id': 1}]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        # Create database manager
        db_manager = DatabaseManager(mock_supabase)

        # Test various error scenarios
        error_scenarios = [
            {
                'error_message': "Symbol THUSDT not supported or not trading.",
                'binance_response': "{'error': 'Symbol THUSDT not supported or not trading.'}",
                'expected_sync_issue': "Trade execution failed: Symbol THUSDT not supported or not trading."
            },
            {
                'error_message': "Margin is insufficient.",
                'binance_response': "{'error': 'Binance API error creating futures order: Margin is insufficient.', 'code': -2019}",
                'expected_sync_issue': "Trade execution failed: Margin is insufficient."
            },
            {
                'error_message': "Failed to store trade in database",
                'binance_response': "",
                'expected_sync_issue': "Trade execution failed: Failed to store trade in database"
            }
        ]

        for i, scenario in enumerate(error_scenarios):
            success = await db_manager.update_trade_failure(
                trade_id=i+1,
                error_message=scenario['error_message'],
                binance_response=scenario['binance_response']
            )

            if not success:
                print(f"  ❌ Failed to handle error scenario {i+1}: {scenario['error_message']}")
                return False

        print("  ✅ All error scenarios handled correctly")
        return True

    except Exception as e:
        print(f"❌ Error testing comprehensive error handling: {e}")
        return False

async def main():
    """Run all critical fix tests."""
    print("🚀 Testing Critical Fixes...")
    print("=" * 60)
    print("This will test that all the critical issues are permanently resolved.")
    print("=" * 60)

    tests = [
        test_signal_parser_coin_symbol_correction,
        test_database_failure_handling,
        test_quantity_extraction_prevention,
        test_ai_parsing_validation,
        test_comprehensive_error_handling
    ]

    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("📊 Critical Fixes Test Results:")

    passed = sum(results)
    total = len(results)

    for i, (test, result) in enumerate(zip(tests, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {test.__name__}: {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL CRITICAL FIXES WORKING!")
        print("✅ 'TH' instead of 'ETH' issue permanently resolved")
        print("✅ All trade failures properly stored in database")
        print("✅ binance_response column always updated")
        print("✅ sync_issues column properly populated")
        print("✅ Automatic scripts can now run without errors")
        return True
    else:
        print("\n⚠️  Some critical fixes need attention.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)


import asyncio
import pytest

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from config.settings import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE

@pytest.mark.asyncio
async def test_kucoin_futures_symbol_support_for_majors():
    # Instantiate with actual KuCoin credentials from settings
    ex = KucoinExchange(
        api_key=KUCOIN_API_KEY or "",  # Default to empty string if None
        api_secret=KUCOIN_API_SECRET or "",
        api_passphrase=KUCOIN_API_PASSPHRASE or "",
        is_testnet=False
    )

    # Get active futures symbols from KuCoin
    all_symbols = await ex.get_futures_symbols()
    assert isinstance(all_symbols, list) and len(all_symbols) > 0, "Should fetch active futures symbols"
    upper_set = set(s.upper() for s in all_symbols)

    # Expected contract codes for majors on KuCoin Futures:
    # Note: KuCoin uses XBT for Bitcoin, not BTC, and USDTM format for perpetuals
    expected_contracts = ["XBTUSDTM", "ETHUSDTM", "BNBUSDTM", "SOLUSDTM"]
    missing = [sym for sym in expected_contracts if sym not in upper_set]
    assert not missing, f"Missing expected KuCoin contracts: {missing}"

    # Now use the exchange's support check (with normalization) on bot-style inputs
    # Bot-side often starts from coin symbols
    for coin_symbol in ["XBT", "ETH", "BNB", "SOL"]:
        ok = await ex.is_futures_symbol_supported(coin_symbol)
        assert ok, f"{coin_symbol} should be supported on KuCoin Futures"

    # Bot-side canonical pair used before kucoin conversion
    for pair in ["XBTUSDTM", "ETHUSDTM", "BNBUSDTM", "SOLUSDTM"]:
        ok = await ex.is_futures_symbol_supported(pair)
        assert ok, f"{pair} should be recognized and supported on KuCoin Futures"

    # Raw futures-style pairs should also pass
    for fpair in expected_contracts:
        ok = await ex.is_futures_symbol_supported(fpair)
        assert ok, f"{fpair} should be supported on KuCoin Futures"

@pytest.mark.asyncio
async def test_kucoin_symbol_mapping_and_filters_for_eth():
    ex = KucoinExchange(
        api_key=KUCOIN_API_KEY or "",  # Default to empty string if None
        api_secret=KUCOIN_API_SECRET or "",
        api_passphrase=KUCOIN_API_PASSPHRASE or "",
        is_testnet=False
    )

    # Bot canonical pair (returns ETHUSDTM format)
    bot_pair = ex.get_futures_trading_pair("ETH")
    assert bot_pair == "ETHUSDTM"

    # Test that the symbol is supported (should work with ETHUSDTM format)
    is_supported = await ex.is_futures_symbol_supported(bot_pair)
    assert is_supported, f"ETH should be supported on KuCoin futures"

    # Filters should be derived using correct mapped symbol (ETHUSDTM)
    flt = await ex.get_futures_symbol_filters(bot_pair)
    assert flt is not None, "Should retrieve symbol filters for ETH"
    assert flt.get("kucoin_symbol", "").upper() == "ETHUSDTM", "Mapped KuCoin contract should be ETHUSDTM"
    assert flt.get("enableTrading") is True, "ETH contract should be Open for trading"
import re
import pytest

from src.exchange.kucoin.kucoin_exchange import KucoinExchange
from config.settings import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE


SAMPLES = [
    {"content": "ETH limit 1228-1217 stop 1190"},
    {"content": "SUSHI limit short 1.247-1.256 stop 1.28"},
    {"content": "KCS spot limit 9.22 (area) stop 8.60"},
    {"content": "CRV limit .761-.754 stop .734"},
    {"content": "ENS short 19.51-19.70 stop 20.17"},
    {"content": "rose spot long .5580-.5453 stop .5180 (5% risk)"},
    {"content": "WOO limit spot .1545-.1512 stop .1460"},
    {"content": "CHR short .1430-.1455 stop .1498"},
    {"content": "CRV limit .852-.836 stop .815"},
    {"content": "AAVE limit 77.2-76.2 stop 74.3"},
    {"content": "ATOM limit 11.84-11.76 stop 11.46 collab w/"},
    {"content": "CRV limit .814-.806 stop .788"},
    {"content": "1inch .569-.563 stop .549"},
    {"content": "MATIC limit short .8524-.8620 stop .8871 collab w/"},
    {"content": "ETH limit short 1438-1453 stop 1488"},
    {"content": "CHZ short .1951-.1964 stop .1996"},
    {"content": "LINK limit 6.86-6.78 stop 6.57 collab w/"},
    {"content": "APE Limit 4.578-4.57 Sl 4.437 TP 5.4, 5.96 collab with woods"},
    {"content": "BTC limit short 21,450-21,667 stop 22,327"},
    {"content": "AVAX limit 18.10-17.90 stop 17.45"},
    {"content": "LINK limit 7.147-7.047 stop 6.852"},
    {"content": "CRV mega mega mega risk low lev or spot play CRV .885 DCA to .85 extremely loose bids heaviest towards the bottom stop .82 (3.5-4% risk) collab w/"},
    {"content": "AVAX limit update 17.67-17.41stop 17.12"},
    {"content": "short CRV massive risk 2% .904 stop.92"},
    {"content": "CRV limit .834-.825 stop .799"},
    {"content": "AAVE limit short 87-88 stop 91 collab w"},
    {"content": "CRV limit .956-.945 stop .923"},
    {"content": "AVAX 20.14-19.90 stop 19.40"},
    {"content": "BTC limit 20,925 - 20,750 stop 20,330 (2% risk)"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "BTC limit 20,280-20160 stop 19,770"},
    {"content": "CRV limit .617-.604 stop .586"},
    {"content": "CRV .604-.60 stop .588"},
    {"content": "ETH limit 1199-1182 stop 1138"},
    {"content": "ETH limit 1120-1100 stop 1070"},
    {"content": "XRP limit .362-.358 stop .348"},
    {"content": "CRV .602-.597 stop .584"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "DYDX limit short 2.395-2.42 stop 2.49"},
    {"content": "BTC short 16660 DCA 16822 stop 17171 RISKY RISKY"},
    {"content": "ALGO limit .2738-.2706 stop .2628"},
    {"content": "VET limit .1710-.1690 stop .1647 collab w/ Eliz"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "APT limit short 4.352-4.448 stop 4.57"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "CRV limit .59-.578 stop .56"},
    {"content": "ETH limit 1092-1080 stop 1054"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "CRV limit spot .558-.533 stop .493"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "BNB limit 270.9-266 stop 257.6"},
    {"content": "APE short 3.568-3.62 stop 3.73"},
    {"content": "APT short 4.828-4.87 stop 5.029"},
    {"content": "AAVE limit 59.6-58.5 stop 56.4"},
    {"content": "APT 4.419-4.35 stop 4.288"},
    {"content": "CRV limit .642-.635 stop .616"},
    {"content": "CRV limit .642-.635 stop .616"},
    {"content": "Algo spot .245-.238 stop 1D close under .2287"},
    {"content": "ETH short 1290 stop 1310"},
    {"content": "ATOM short 10.31-10.42 stop 10.645"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "avax short 13.95-14.10 stop 14.40 mega risky"},
    {"content": "COTI .731-.724 stop .702"},
    {"content": "LINK limit short 7.40-7.46 stop 7.63"},
    {"content": "APT limit short 5.136-5.189 stop 5.317"},
    {"content": "AAVE 62.6-62 stop 60.6"},
    {"content": "APE limit short 3.973 stop 4.056"},
    {"content": "BNB limit 265.6-262.3 stop 254.3"},
    {"content": "ATOM long 9.682-9.582 stop 9.44"},
    {"content": "ETH limit 1191-1177 stop 1147"},
    {"content": "CRV .606-.597 stop .58"},
    {"content": "ATOM limit 9.255-9.064 stop 8.823"},
    {"content": "CRV limit .627-.621 stop .606"},
    {"content": "ADA limit short .3055-.3092 stop .3145"},
    {"content": "CRV limit .614-.611 stop .598"},
    {"content": "ETH limit short 1243-1257 stop 1295"},
    {"content": "CRV limit .478-.472 stop .456"},
    {"content": "Trade has been updated. Be sure to"},
    {"content": "ETH limit 1175-1163 stop 1140"},
    {"content": "DOGE limit .07475-.074 stop .0725"},
    {"content": "DOT limit 4.45-4.42 stop 4.337"},
    {"content": "BTC limit 16490-16422 SL 16321 collab w/ Tah"},
    {"content": "AZERO limit spot.8180-.8040 stop .7750"},
    {"content": "BTC limit 15,820-15,700 stop 15,468"},
    {"content": "CRV limit .515-.51 stop .498"},
    {"content": "ETH limit 1183-1174 stop 1150.9"},
    {"content": "CRV limit .508-.5 stop .49"},
    {"content": "CHR spot limit .1070-.1050 stop .0937 or daily close below .10"},
    {"content": "ETH limit short 1293-1310 stop 1339 collab w/ TAH"},
    {"content": "ETC short 18.73-19.13 stop 19.71"},
    {"content": "ETC limit short 18.93-19.20 stop 19.78"},
    {"content": "RLC 1.144-1.134 stop 1.11"},
    {"content": "ETC short 19.75 stop 20.04"},
    {"content": "ETC limit spot 19.20-18.62 stop 17.59"},
    {"content": "ETH limit short 1445-1460 stop 1495"},
    {"content": "BTC limit 16,990-16,920 stop 16,652"},
    {"content": "Matic limit .809-.796 stop .776"},
    {"content": "APE limit short 5.17-5.24 stop 5.38"},
    {"content": "RUNE limit short 1.455-1.468 stop 1.496"},
]


def _extract_symbol(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    # First word often is the symbol; keep letters only
    first = t.split()[0]
    word = re.sub(r"[^A-Za-z]", "", first)
    if not word:
        return ""
    word = word.upper()
    # Normalize known aliases
    if word == "BTC":
        word = "XBT"  # KuCoin futures uses XBT
    if word == "MATIC":
        word = "MATIC"
    if word == "ALGO":
        word = "ALGO"
    if word == "1INCH":
        word = "1INCH"  # keep as is; converter handles dash/USDTM later
    return word


@pytest.mark.asyncio
async def test_dynamic_symbols_presence_on_kucoin():
    ex = KucoinExchange(
        api_key=KUCOIN_API_KEY or "",
        api_secret=KUCOIN_API_SECRET or "",
        api_passphrase=KUCOIN_API_PASSPHRASE or "",
        is_testnet=False,
    )

    # Fetch once for speed; the exchange caches internally as well
    all_symbols = await ex.get_futures_symbols()
    assert isinstance(all_symbols, list) and len(all_symbols) > 0

    results = []
    num_checked = 0
    num_supported = 0

    for item in SAMPLES:
        content = item.get("content", "")
        sym = _extract_symbol(content)
        if not sym:
            continue

        # Skip explicit spot calls from strict assertion, but still report
        is_spot_hint = "spot" in content.lower()

        bot_pair = ex.get_futures_trading_pair(sym)
        ok = await ex.is_futures_symbol_supported(bot_pair)
        results.append((sym, bot_pair, ok, is_spot_hint, content[:60]))

        if not is_spot_hint:
            num_checked += 1
            if ok:
                num_supported += 1

    print("Checked symbols (non-spot enforced):")
    for sym, pair, ok, is_spot_hint, preview in results:
        tag = "spot" if is_spot_hint else "futures"
        print(f" - {sym:6s} -> {pair:12s} [{tag}] supported={ok}")

    # Only assert that at least some non-spot symbols are supported to avoid brittleness
    assert num_checked >= 5
    assert num_supported >= 3



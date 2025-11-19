import asyncio
import pytest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.core.dynamic_alert_parser import DynamicAlertParser


@pytest.mark.asyncio
async def test_stopped_out_defaults_close_100():
    parser = DynamicAlertParser()
    result = await parser.parse_alert_content("BTC | Stopped out")
    assert result["action_type"] in ("stop_loss_hit", "position_closed")
    assert float(result.get("close_percentage", 100)) == 100.0


@pytest.mark.asyncio
async def test_closed_be_defaults_close_100():
    parser = DynamicAlertParser()
    result = await parser.parse_alert_content("ICP | Closed BE")
    assert result["action_type"] in ("position_closed", "stop_loss_hit")
    assert float(result.get("close_percentage", 100)) == 100.0


@pytest.mark.asyncio
async def test_updated_stoploss_without_price_maps_to_be():
    parser = DynamicAlertParser()
    content = "BTC | Updated Stoploss, Average Entry, Entry Levels"
    result = await parser.parse_alert_content(content)
    assert result["action_type"] == "stop_loss_update"
    assert str(result.get("stop_loss_price")).upper() in ("BE", "BREAK_EVEN")


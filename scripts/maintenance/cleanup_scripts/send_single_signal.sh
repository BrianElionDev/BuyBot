#!/bin/bash
curl -X POST http://0.0.0.0:8001/api/v1/discord/signal \
-H "Content-Type: application/json" \
-d '{
  "timestamp": "2025-06-05T20:56:11.028Z",
  "content": "@-JDrip ETH limit long 2350-2250 SL 2150",
  "structured": "LIMIT|ETH|Entry:|2350-2250|SL:|2150"
}'

(venv) ngigi@saitama:~/Documents/Brayo/rubicon-trading-bot$ python3 -m discord_bot.main
2025-07-01 11:53:01,145 - __main__ - INFO - [DiscordSvc] - 🚀 Starting Discord Bot Service...
INFO:     Started server process [415422]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001 (Press CTRL+C to quit)
INFO:     127.0.0.1:60486 - "POST /api/v1/discord/signal HTTP/1.1" 200 OK
2025-07-01 11:53:42,018 - discord_bot.discord_bot - INFO - [DiscordSvc] - Processing initial signal: LIMIT|TAO|Entry:|313-295|SL:|284.4
2025-07-01 11:53:42,018 - discord_bot.database - INFO - [DiscordSvc] - Querying for timestamp: original='2025-06-05T14:17:51.472Z', cleaned='2025-06-05 14:17:51.472'
2025-07-01 11:53:44,534 - httpx - INFO - [DiscordSvc] - HTTP Request: GET https://tdvksazoohmjjnwjdqmy.supabase.co/rest/v1/trades?select=%2A&timestamp=gte.2025-06-05T14%3A17%3A51.472000&timestamp=lt.2025-06-05T14%3A17%3A51.473000&order=timestamp.desc&limit=1 "HTTP/2 200 OK"
2025-07-01 11:53:44,538 - discord_bot.database - INFO - [DiscordSvc] - Found trade by timestamp range for 2025-06-05 14:17:51.472: ID 83
2025-07-01 11:53:44,539 - discord_bot.discord_bot - INFO - [DiscordSvc] - Parsing signal content with AI: '@Johnny TAO limit 313 - 295 sl 284.4'
2025-07-01 11:53:50,290 - httpx - INFO - [DiscordSvc] - HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
2025-07-01 11:53:50,293 - discord_bot.discord_signal_parser - INFO - [DiscordSvc] - OpenAI parsed data: {'coin_symbol': 'TAO', 'position_type': 'LONG', 'entry_prices': [313, 295], 'stop_loss': 284.4, 'take_profits': None, 'order_type': 'LIMIT', 'risk_level': None}
2025-07-01 11:53:51,829 - httpx - INFO - [DiscordSvc] - HTTP Request: PATCH https://tdvksazoohmjjnwjdqmy.supabase.co/rest/v1/trades?id=eq.83 "HTTP/2 200 OK"
2025-07-01 11:53:51,833 - discord_bot.database - INFO - [DiscordSvc] - Updated trade with: {'parsed_signal': {'coin_symbol': 'TAO', 'position_type': 'LONG', 'entry_prices': [313, 295], 'stop_loss': 284.4, 'take_profits': None, 'order_type': 'LIMIT', 'risk_level': None}}
2025-07-01 11:53:51,834 - discord_bot.discord_bot - INFO - [DiscordSvc] - Successfully stored parsed signal for trade ID: 83
2025-07-01 11:53:51,834 - discord_bot.discord_bot - INFO - [DiscordSvc] - Processing trade with TradingEngine using parameters: {'coin_symbol': 'TAO', 'signal_price': 313.0, 'position_type': 'LONG', 'sell_coin': 'USDT', 'order_type': 'LIMIT', 'stop_loss': 284.4, 'take_profits': None, 'exchange_type': 'cex'}
2025-07-01 11:53:51,834 - src.bot.trading_engine - INFO - [DiscordSvc] - Processing CEX signal: TAO @ $313.0
2025-07-01 11:53:51,834 - src.bot.trading_engine - INFO - [DiscordSvc] - Order Type: LIMIT
2025-07-01 11:53:51,834 - src.bot.trading_engine - INFO - [DiscordSvc] - Stop Loss: $284.4
2025-07-01 11:53:53,615 - src.services.price_service - INFO - [DiscordSvc] - Found 4 candidates for symbol TAO. Evaluating best match...
2025-07-01 11:53:54,387 - src.services.price_service - INFO - [DiscordSvc] - Best match by market cap for TAO: bittensor
2025-07-01 11:53:55,358 - src.services.price_service - INFO - [DiscordSvc] - Price for bittensor: $330.38
2025-07-01 11:53:55,358 - src.exchange.binance_exchange - INFO - [DiscordSvc] - Attempting to fetch USDⓈ-M futures balance...
2025-07-01 11:53:56,948 - src.exchange.binance_exchange - INFO - [DiscordSvc] - Successfully fetched USDⓈ-M futures balance.
2025-07-01 11:53:56,948 - src.bot.trading_engine - INFO - [DiscordSvc] - Available USDT balance on Binance Futures: $11.46255464
2025-07-01 11:53:56,948 - src.bot.trading_engine - WARNING - [DiscordSvc] - Trade amount $0.11 below minimum $10.0
2025-07-01 11:53:58,469 - httpx - INFO - [DiscordSvc] - HTTP Request: PATCH https://tdvksazoohmjjnwjdqmy.supabase.co/rest/v1/trades?id=eq.83 "HTTP/2 200 OK"
2025-07-01 11:53:58,470 - discord_bot.database - INFO - [DiscordSvc] - Updated trade with: {'status': 'FAILED'}
2025-07-01 11:53:58,470 - discord_bot.discord_bot - ERROR - [DiscordSvc] - Trade processing failed for trade ID: 83. Reason: Trade amount $0.11 below minimum $10.0
2025-07-01 11:53:58,471 - discord_bot.discord_endpoint - ERROR - [DiscordSvc] - Failed to process initial signal: Trade processing failed: Trade amount $0.11 below minimum $10.0
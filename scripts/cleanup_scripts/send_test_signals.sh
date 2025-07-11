#!/bin/bash
#
# This script sends test signals extracted from the image to the bot's API endpoint.
# A 1-second delay is added between requests to prevent rate-limiting or other issues.
#
# To run this script:
# 1. Make sure your bot's server is running.
# 2. Open a terminal in your project directory.
# 3. Make the script executable by running: chmod +x scripts/send_test_signals.sh
# 4. Execute the script: ./scripts/send_test_signals.sh
#

API_URL="http://0.0.0.0:8001/api/v1/discord/signal"

# Function to send a request
send_request() {
  local data="$1"
  echo "Sending signal to $API_URL"
  echo "Data: $data"
  curl -X POST -H "Content-Type: application/json" -d "$data" "$API_URL"
  echo -e "\n----------------------------------------------------------\n"
  sleep 1
}

send_request '{
  "timestamp": "2025-06-05T14:17:51.472Z",
  "content": "@Johnny TAO limit 313 - 295 sl 284.4",
  "structured": "LIMIT|TAO|Entry:|313-295|SL:|284.4"
}'

send_request '{
  "timestamp": "2025-06-05T14:19:26.013Z",
  "content": "@-Tareeq shorted major at 0.262 SL: 0.2765 (1% risk)",
  "structured": "MAJOR|Entry:|0.262|SL:|0.2765"
}'

send_request '{
  "timestamp": "2025-06-05T14:26:56.271Z",
  "content": "@HBJ ETH low lev limit long 2465-2380 SL 30m close bel",
  "structured": "LIMIT|ETH|Entry:|2465-2380|SL:|30m < 2240"
}'

send_request '{
  "timestamp": "2025-06-05T14:42:26.464Z",
  "content": "@-Muzzagin Launchcoin long 0.148 - 0.0142 Sl: 0.138",
  "structured": "LAUNCHCOIN|Entry:|0.148-0.142|SL:|0.138"
}'

send_request '{
  "timestamp": "2025-06-05T14:48:08.795Z",
  "content": "@-Mouse Longed HUMA Entry: 0.0402 SL: 0.03853",
  "structured": "HUMA|Entry:|0.0402|SL:|BE|TPs:|0.04191"
}'

send_request '{
  "timestamp": "2025-06-05T14:55:11.789Z",
  "content": "@HBJ Hype low lev limit long 29.6-28.13 SL 1h close below",
  "structured": "LIMIT|HYPE|Entry:|29.6-28.13|SL:|1H < 25.3"
}'

send_request '{
  "timestamp": "2025-06-05T15:02:20.313Z",
  "content": "@-Muzzagin Fartcoin long 0.941 - 0.913 Sl: 0.885",
  "structured": "FARTCOIN|Entry:|0.941-0.913 (|AVG:|0.9362)|SL:|BE|TPs:|0.9676"
}'

send_request '{
  "timestamp": "2025-06-05T15:10:03.052Z",
  "content": "@HBJ Fartcoin low lev limit long 0.8162-0.7530 SL 1h clos",
  "structured": "LIMIT|FARTCOIN|Entry:|0.8162-0.7530|SL:|1H < 0.63"
}'

send_request '{
  "timestamp": "2025-06-05T15:23:48.489Z",
  "content": "@Johnny Longed eth 2590 sl 2553",
  "structured": "ETH|Entry:|2590|SL:|BE"
}'

send_request '{
  "timestamp": "2025-06-05T15:41:12.792Z",
  "content": "@Johnny fartcoin .96 - .92 SL .86",
  "structured": "FARTCOIN|Entry:|0.96-0.92|SL:|BE"
}'

send_request '{
  "timestamp": "2025-06-05T16:54:40.998Z",
  "content": "@Johnny Eth 2558 - 2542 sl 2472",
  "structured": "ETH|Entry:|2558-2542|SL:|2472"
}'

send_request '{
  "timestamp": "2025-06-05T16:58:38.639Z",
  "content": "@Johnny Fartcoin $.934 - $.912 sl $.857",
  "structured": "FARTCOIN|Entry:|0.934-0.912|SL:|BE|TPs:|1.0285"
}'

send_request '{
  "timestamp": "2025-06-05T17:20:46.221Z",
  "content": "@Johnny Longed BTC 103500 sl 100329",
  "structured": "BTC|Entry:|103500|SL:|100329"
}'

send_request '{
  "timestamp": "2025-06-05T17:25:39.576Z",
  "content": "@-Tareeq eth limit long: 2405 SL: 2336 (2,5% risk)",
  "structured": "ETH|Entry:|2405|SL:|BE"
}'

send_request '{
  "timestamp": "2025-06-05T19:19:33.581Z",
  "content": "@-Muzzagin Fartcoin long 0.918 - 0.89 Sl: 0.87",
  "structured": "FARTCOIN|Entry:|0.918-0.89 (|AVG:|0.9172)|SL:|BE|TPs:|0.9704, 0.9826"
}'

send_request '{
  "timestamp": "2025-06-05T19:36:20.974Z",
  "content": "@-Tareeq longed fartcoin at 0.973 SL: 0.9405 (1% risk)",
  "structured": "FARTCOIN|Entry:|0.973|SL:|0.9405"
}'

send_request '{
  "timestamp": "2025-06-05T20:27:21.950Z",
  "content": "@-DB ETH spot limit 2008 SL 4H close below 1960",
  "structured": "LIMIT|ETH|Entry:|2008|SL:|4H < 1960"
}'

send_request '{
  "timestamp": "2025-06-05T20:47:20.317Z",
  "content": "@Eliz Long zen 10 9.50 stop 8.98",
  "structured": "ZEN|Entry:|10-9.5|SL:|8.98"
}'

send_request '{
  "timestamp": "2025-06-05T20:55:18.667Z",
  "content": "@-Muzzagin hype limit 32.2 - 31.5 sl 30.7",
  "structured": "LIMIT|HYPE|Entry:|32.2-31.5|SL:|30.7"
}'

send_request '{
  "timestamp": "2025-06-05T20:56:11.028Z",
  "content": "@-JDrip ETH limit long 2350-2250 SL 2150",
  "structured": "LIMIT|ETH|Entry:|2350-2250|SL:|2150"
}'

echo "All signals from the image have been sent."


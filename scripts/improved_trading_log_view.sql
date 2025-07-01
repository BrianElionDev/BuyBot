-- Improved Trading Log View
-- This view combines trades and alerts to show the complete lifecycle of each trade

CREATE OR REPLACE VIEW public.enhanced_trading_log AS
-- Initial trade entries
SELECT
    t.timestamp,
    'Initial Signal' as text_of_signal,
    t.trader,
    'entry' as state,
    t.parsed_signal ->> 'coin_symbol' as coin,
    CONCAT(
        t.parsed_signal ->> 'position_type',
        ' ',
        t.parsed_signal ->> 'coin_symbol',
        ' limit ',
        (t.parsed_signal -> 'entry_prices' ->> 0)
    ) as action_1,
    CONCAT('Stop loss (', t.parsed_signal ->> 'position_type', ') ', t.parsed_signal ->> 'stop_loss') as action_2,
    CASE
        WHEN t.status = 'CLOSED' THEN 'Revealed after the fact'
        ELSE 'Not revealed'
    END as take_profit,
    t.discord_id as trade_id,
    1 as sort_order
FROM trades t
WHERE t.parsed_signal IS NOT NULL

UNION ALL

-- Follow-up alerts
SELECT
    a.timestamp,
    a.content as text_of_signal,
    a.trader,
    'follow-up' as state,
    a.parsed_alert ->> 'coin_symbol' as coin,
    CASE
        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'stop_loss_hit'
        THEN CONCAT('Stop loss (sell) ', a.parsed_alert ->> 'coin_symbol')

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'position_closed'
        THEN CONCAT('Position closed ', a.parsed_alert ->> 'coin_symbol')

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'take_profit_1'
        THEN CONCAT('Take profit (sell) ', a.parsed_alert ->> 'coin_symbol', ' TP1')

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'take_profit_2'
        THEN CONCAT('Take profit (sell) ', a.parsed_alert ->> 'coin_symbol', ' TP2')

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'stop_loss_update'
        THEN CONCAT('Stop loss changed to break even for ', a.parsed_alert ->> 'coin_symbol')

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'order_cancelled'
        THEN CONCAT('Limit order cancelled for ', a.parsed_alert ->> 'coin_symbol')

        ELSE a.parsed_alert -> 'action_determined' ->> 'action_description'
    END as action_1,

    CASE
        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'stop_loss_update'
        THEN 'Stop loss changed to purchase price'

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'take_profit_1'
        THEN 'Take profit (remaining position)'

        ELSE NULL
    END as action_2,

    CASE
        WHEN a.parsed_alert -> 'action_determined' ->> 'position_status' = 'CLOSED'
        THEN 'Revealed after the fact'

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'take_profit_1'
        THEN 'TP1 appears'

        WHEN a.parsed_alert -> 'action_determined' ->> 'action_type' = 'take_profit_2'
        THEN 'TP2 appears'

        ELSE 'None at first, they appear later'
    END as take_profit,

    a.trade as trade_id,
    2 as sort_order

FROM alerts a
WHERE a.parsed_alert IS NOT NULL

ORDER BY trade_id, timestamp, sort_order;
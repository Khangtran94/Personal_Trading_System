-- 5.1. Theo ngày
SELECT 
    DATE(timestamp) AS trade_date,
    COUNT(*) AS trades,
    SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS wins,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY DATE(timestamp)
ORDER BY trade_date;

-- 5.2. Theo giờ (session)
SELECT 
    strftime('%H', timestamp) AS hour,
    COUNT(*) AS trades,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY hour
ORDER BY hour;

-- 5.3. Equity curve (Sum R theo thời gian) – dùng để vẽ
SELECT 
    timestamp,
    r_multiple,
    SUM(r_multiple) OVER (ORDER BY timestamp) AS cum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
ORDER BY timestamp;
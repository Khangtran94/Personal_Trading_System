-- Top tốt nhất (theo Avg R, tối thiểu 5 lệnh)
SELECT 
    symbol,
    COUNT(*) AS trades,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY symbol
HAVING COUNT(*) >= 5
ORDER BY avg_r DESC
LIMIT 15;

-- Top tệ nhất
SELECT 
    symbol,
    COUNT(*) AS trades,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY symbol
HAVING COUNT(*) >= 5
ORDER BY avg_r ASC
LIMIT 15;
-- 1.1. Phân bố kết quả
SELECT 
    COALESCE(result, 'OPEN') AS status,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM signals
GROUP BY COALESCE(result, 'OPEN')
ORDER BY cnt DESC;

-- 1.2. Win rate + Avg R + Sum R + Expectancy (chỉ tính WIN/LOSS)
SELECT 
    COUNT(*) AS closed_trades,
    SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 4) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r,
    -- Expectancy = (WinRate * AvgWin) + (LossRate * AvgLoss)
    ROUND(
        (SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)) * 
        AVG(CASE WHEN result = 'WIN' THEN r_multiple END)
        +
        (SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)) * 
        AVG(CASE WHEN result = 'LOSS' THEN r_multiple END)
    , 3) AS expectancy
FROM signals
WHERE result IN ('WIN', 'LOSS');
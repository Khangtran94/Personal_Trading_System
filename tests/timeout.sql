SELECT 
    COUNT(*) AS total_signals,
    SUM(CASE WHEN result = 'TIMEOUT' THEN 1 ELSE 0 END) AS timeouts,
    ROUND(SUM(CASE WHEN result = 'TIMEOUT' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS timeout_pct,
    ROUND(AVG(CASE WHEN result = 'TIMEOUT' THEN r_multiple END), 3) AS avg_r_timeout,
    ROUND(SUM(CASE WHEN result = 'TIMEOUT' THEN r_multiple ELSE 0 END), 2) AS sum_r_timeout
FROM signals
WHERE result IS NOT NULL;   -- loại OPEN
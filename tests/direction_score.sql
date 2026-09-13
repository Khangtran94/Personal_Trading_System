SELECT 
    direction,
    COUNT(*) AS trades,
    SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS wins,
    SUM(CASE WHEN result = 'LOSS' THEN 1 ELSE 0 END) AS losses,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r,
    ROUND(AVG(CASE WHEN result = 'WIN' THEN r_multiple END), 3) AS avg_win_r,
    ROUND(AVG(CASE WHEN result = 'LOSS' THEN r_multiple END), 3) AS avg_loss_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY direction
ORDER BY direction;

SELECT 
    score,
    direction,
    COUNT(*) AS trades,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY score, direction
ORDER BY score DESC, direction;

-- Tổng hợp không phân biệt direction (để nhìn xu hướng score)
SELECT 
    score,
    COUNT(*) AS trades,
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*), 3) AS win_rate,
    ROUND(AVG(r_multiple), 3) AS avg_r,
    ROUND(SUM(r_multiple), 2) AS sum_r
FROM signals
WHERE result IN ('WIN', 'LOSS')
GROUP BY score
ORDER BY score DESC;
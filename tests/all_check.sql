SELECT direction, result, count(*)
FROM signals
where result IN ('WIN','LOSS')
GROUP BY 1,2;

SELECT score,direction, result, count(*)
FROM signals
where result IN ('WIN','LOSS')
GROUP BY 1,2,3;

with numbered AS
(SELECT timestamp, result, 
        ROW_NUMBER() OVER(ORDER BY timestamp) AS rn,
        ROW_NUMBER() OVER(PARTITION BY result ORDER BY timestamp) AS result_rn
FROM signals
where result IN ('WIN','LOSS')),

groups AS
(SELECT result, rn - result_rn AS grp
FROM numbered),

length AS
(SELECT result, grp, COUNT(*) AS streak
FROM groups 
GROUP BY 1,2)

SELECT result, streak, COUNT(*) AS times
FROM length
WHERE streak > 3
GROUP BY 1,2 
ORDER BY 1,2;

SELECT score,direction,
    COUNT(*) AS cnt, 
    ROUND(SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) * 1.0 / COUNT(*),2) AS win_rate,
    ROUND(AVG(r_multiple),2) AS avg_r,
    ROUND(SUM(r_multiple),2) AS sum_r
FROM signals
WHERE result IN ('WIN','LOSS')
GROUP BY 1,2
ORDER BY 1,2;


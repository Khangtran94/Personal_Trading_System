-- 2.1. Max Winning / Losing Streak
WITH numbered AS (
    SELECT 
        timestamp,
        result,
        ROW_NUMBER() OVER (ORDER BY timestamp) AS rn,
        ROW_NUMBER() OVER (PARTITION BY result ORDER BY timestamp) AS result_rn
    FROM signals
    WHERE result IN ('WIN', 'LOSS')
),
groups AS (
    SELECT 
        result,
        rn - result_rn AS grp
    FROM numbered
),
streaks AS (
    SELECT 
        result,
        COUNT(*) AS streak_len
    FROM groups
    GROUP BY result, grp
)
SELECT 
    result,
    MAX(streak_len) AS max_streak
FROM streaks
GROUP BY result;

-- 2.2. Current streak (chuỗi đang chạy)
WITH ordered AS (
    SELECT 
        result,
        ROW_NUMBER() OVER (ORDER BY timestamp DESC) AS rn
    FROM signals
    WHERE result IN ('WIN', 'LOSS')
),
current_group AS (
    SELECT result
    FROM ordered
    WHERE rn = 1
)
SELECT 
    o.result AS current_result,
    COUNT(*) AS current_streak
FROM ordered o
CROSS JOIN current_group cg
WHERE o.result = cg.result
  AND o.rn <= (
      SELECT MIN(rn) - 1 
      FROM ordered 
      WHERE result != cg.result
  ) + 1   -- đếm đến khi gặp kết quả khác
GROUP BY o.result;

-- Cách đơn giản hơn (thường dùng):
WITH ordered AS (
    SELECT result, timestamp
    FROM signals
    WHERE result IN ('WIN', 'LOSS')
    ORDER BY timestamp DESC
)
SELECT 
    result AS current_result,
    COUNT(*) AS current_streak
FROM (
    SELECT result,
           SUM(CASE WHEN result != LAG(result) OVER (ORDER BY timestamp DESC) THEN 1 ELSE 0 END) 
               OVER (ORDER BY timestamp DESC) AS grp
    FROM ordered
) t
WHERE grp = 0
GROUP BY result;

-- 2.3. Max Drawdown theo R (từ đỉnh equity curve)
WITH equity AS (
    SELECT 
        timestamp,
        r_multiple,
        SUM(r_multiple) OVER (ORDER BY timestamp) AS cum_r
    FROM signals
    WHERE result IN ('WIN', 'LOSS')
),
peaks AS (
    SELECT 
        timestamp,
        cum_r,
        MAX(cum_r) OVER (ORDER BY timestamp) AS peak_r
    FROM equity
)
SELECT 
    ROUND(MAX(peak_r - cum_r), 2) AS max_drawdown_R,
    ROUND(MIN(cum_r - peak_r), 2) AS max_drawdown_R_negative   -- sẽ là số âm
FROM peaks;
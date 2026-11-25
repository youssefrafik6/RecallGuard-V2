WITH grouped AS (
    SELECT COALESCE(NULLIF(category, ''), 'Unspecified') AS category,
           COUNT(*) AS reports,
           COUNT(*) FILTER (WHERE label_recalled = 1) AS linked_reports
    FROM incidents
    GROUP BY 1
)
SELECT *, DENSE_RANK() OVER (ORDER BY reports DESC) AS volume_rank
FROM grouped
ORDER BY reports DESC, category
LIMIT 100

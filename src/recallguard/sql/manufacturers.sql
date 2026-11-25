SELECT COALESCE(NULLIF(manufacturer, ''), 'Unspecified') AS manufacturer,
       COUNT(*) AS reports,
       COUNT(*) FILTER (WHERE label_recalled = 1) AS linked_reports
FROM incidents
GROUP BY 1
ORDER BY reports DESC, manufacturer
LIMIT 25

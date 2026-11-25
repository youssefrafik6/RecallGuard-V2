SELECT CAST(DATE_TRUNC('month', report_date) AS DATE) AS month,
       COUNT(*) AS reports,
       COUNT(*) FILTER (WHERE label_recalled = 1) AS linked_reports
FROM incidents
WHERE report_date IS NOT NULL
GROUP BY 1
ORDER BY 1

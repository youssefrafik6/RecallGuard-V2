SELECT COUNT(*) AS reports,
       COUNT(*) FILTER (WHERE label_recalled = 1) AS linked_reports,
       COUNT(*) FILTER (WHERE label_recalled IS NULL) AS unlabeled_reports,
       COUNT(*) FILTER (WHERE report_date IS NULL) AS missing_report_dates,
       COUNT(*) FILTER (WHERE COALESCE(manufacturer, '') = '') AS missing_manufacturers
FROM incidents

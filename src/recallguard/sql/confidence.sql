SELECT confidence, COUNT(*) AS candidate_pairs, COUNT(DISTINCT report_id) AS reports
FROM candidates
GROUP BY 1
ORDER BY candidate_pairs DESC, confidence

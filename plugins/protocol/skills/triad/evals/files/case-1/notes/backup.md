# Backups

Every night at 01:30 the backup job exports the wiki through its API
(http://officebox:8080/api/export) and copies the file to the NAS.

Keep 14 days. Check the NAS folder on Mondays.

# Disk space on the office server

Drive C: 61 GB free of 250. Drive D: 112 GB free of 2000, which is 5.6%.
The largest folders on D are the render cache (640 GB), old project
archives (510 GB) and the wiki data with its backups (95 GB). The render
cache has no cleanup rule and has grown 40 GB a week since September.
At that pace D is full in under three weeks. Proposal: delete cache files
older than 30 days now (frees about 400 GB) and add a weekly cleanup job.

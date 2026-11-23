Rough notes on what a good answer does:

- spots the cause (files with uppercase extensions like .JPG get skipped,
  the filter compares against ".jpg")
- proposes a fix, e.g. lowercasing the extension before comparing
- explains clearly and says how to confirm it
- no laundry list of maybe-causes
- under 150 words
- fyi the real bug is in filter.py line 12, they don't need to say that

# wordcount.py

A small command-line tool. Python 3, standard library only.

## What it does

`python wordcount.py FILE` reads a text file (UTF-8) and prints its most
frequent words, most frequent first, one per line, as `word count`
separated by one space.

- A word is a run of letters. Everything else separates words.
- Counting ignores case; words are printed in lower case.
- Words with the same count are printed in alphabetical order.

## Options

- `--top N`: how many words to print. Default 10. N must be 1 or more.
- `--min-length L`: leave out words shorter than L letters. Default 1.

## Errors

- FILE does not exist: print `No such file: FILE` to standard error and
  exit with code 2.
- `--top 0` or a negative number: print `--top must be 1 or more` to
  standard error and exit with code 2.

## Tests

`tests/test_wordcount.py`, using `unittest`. Cover at least: a normal
file, the case rule, the tie rule, both options, and both errors.
`python -m unittest discover -s tests` has to pass.

## Not wanted

- No list of words to skip, such as "the" and "and".
- No other output formats, such as JSON or CSV.
- No reading from standard input.
- No packaging files, no README.

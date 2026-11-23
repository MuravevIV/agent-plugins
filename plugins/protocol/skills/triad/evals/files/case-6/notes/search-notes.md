# Search notes: config loading

Notes from a quick search of the code, done by Haiku.

- `load_config` is defined in `src/app/config.py`.
- It is called from `src/app/cli.py` and `src/app/worker.py`.
- Default timeout is 30 seconds. Default retries is 3.
- The path of the config file can be set with the environment variable
  `APP_CONFIG`. Without it the file `config.json` in the current folder
  is used.
- A missing config file is not an error; the defaults are used.

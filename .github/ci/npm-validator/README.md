# CI-only Splunk NPM validator

Each `engines/` directory is an isolated, exact NPM lock. CI installs one lock, builds the
Enterprise preset schema, and streams the Python-generated JSONL corpus through
`DashboardValidator` and the official Dynamic Options Syntax parser.

These files are development infrastructure. They are excluded from Python source and wheel
artifacts, and this project does not redistribute the downloaded packages or generated schemas.
The runner's optional `--schema-output` flag is intended for ephemeral local inspection in an
environment where the caller has installed and accepted the applicable package licenses.

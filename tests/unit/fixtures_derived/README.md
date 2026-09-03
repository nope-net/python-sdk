# Source-derived error bodies

The live capture run (see `tests/fixtures/README.md`) cannot produce a 402, 403,
410, 429 or 503 on demand, so these bodies are transcribed from the API source.
Each file names its source lines in a `_source` key and any headers the route
sets alongside the body in `_headers`. The test loader strips underscore keys.

Re-transcribe a file when the cited lines change.

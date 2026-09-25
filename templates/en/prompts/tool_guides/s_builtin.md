# Tool Usage Guide

### Background Command Output
Long-running commands write output to `state/cmd_output/`. Use `Read(path="state/cmd_output/{id}.txt")` to check intermediate output.
Commands that may take up to ~20 minutes (e.g. heavy tests) should be run in the background and polled every few minutes to track progress.

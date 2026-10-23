#!/usr/bin/env sh
# Works even when launched from outside the project directory.
cd "$(dirname "$0")" || exit 1
exec python3 start.py "$@"

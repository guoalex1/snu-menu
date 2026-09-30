#!/bin/bash
# Entry point for the scheduled task; main.py reads .env itself.
cd "$(dirname "$0")" || exit 1
export PATH="$HOME/.local/bin:$PATH"
{
    echo "=== $(date '+%F %T %Z')"
    python3 main.py
} >> menu.log 2>&1

#!/bin/bash
# Double-click in Finder. Runs locally; never changes or uploads a dictionary.
cd -- "$(dirname -- "$0")" || exit 1
python3 validate_hungarian.py --open-results
validation_status=$?
read -r -p "Press Return to close this window. "
exit "$validation_status"

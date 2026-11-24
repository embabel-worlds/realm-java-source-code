#!/bin/sh
# Live battery for realm-java-source-code: every view by name, then exact reconciliation against
# the sources jar this realm ships, read here with Python's zipfile.
#
#   APPLIANCE=http://127.0.0.1:8080 AUTH=user:pass sh tests/verify.sh
#
# The realm reads sources it ships (data/sources/), over the jar realm-java-code ships, so it needs no
# source key. Its last line on success is exactly `ALL CHECKS PASS`; any failure exits non-zero.
set -e
cd "$(dirname "$0")/.."
: "${AUTH:?set AUTH=user:pass for the target appliance}"
APPLIANCE="${APPLIANCE:-http://127.0.0.1:8080}" exec python3 tests/verify.py

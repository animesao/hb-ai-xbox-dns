#!/usr/bin/env bash
# Тесты HB AI · Smart DNS для Linux.
set -euo pipefail
cd "$(dirname "$0")"

python3 tests.py

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .build/tmp
export TMPDIR="$PWD/.build/tmp"
g++ -std=c++11 -Wall -Wextra -Werror -pedantic -Iinclude test/native/control_logic_test.cpp -o .build/control_logic_test
.build/control_logic_test

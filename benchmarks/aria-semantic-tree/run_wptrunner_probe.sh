#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 3 ]]; then
  echo "Usage: $0 /path/to/wpt /path/to/lightpanda /path/to/venv/bin/python [wpt-test-path]" >&2
  exit 2
fi
WPT="$(realpath "$1")"
BINARY="$(realpath "$2")"
PYTHON="$3"  # Retain venv entrypoint: realpath would resolve to system Python.
TEST="${4:-wai-aria/idlharness.window.html}"
export PYTHONPATH="$WPT:$WPT/tools/wptserve:$WPT/tools/wptrunner:$WPT/tools/manifest:$WPT/tools/webdriver:$WPT/tools/third_party/h2/src:$WPT/tools/third_party/hpack/src:$WPT/tools/third_party/hyperframe/src:$WPT/tools/third_party/pywebsocket3"
cd "$WPT"
timeout 75s "$PYTHON" -c 'from wptrunner.wptrunner import main; raise SystemExit(main())' \
  --product lightpanda \
  --binary "$BINARY" \
  --tests "$WPT" \
  --metadata "$WPT" \
  --manifest-update \
  --no-manifest-download \
  --processes 1 \
  "$TEST"

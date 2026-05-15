#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build the macOS Cuttlefish launcher path without pulling in the linux_musl
# cvd-host package that droidcore depends on.
"${SCRIPT_DIR}/build-aosp-full.sh" cvd_internal_start cvd_internal_stop

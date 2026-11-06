#!/usr/bin/env bash
# Fetch the published ACWF reference runs used by 4-analyze for the cross-code
# comparison (config.ACWF_REFERENCE_OUTPUTS_DIR).
#
# The two all-electron averages needed for Delta/nu/epsilon are already shipped
# in data/reference/; this script only provides the per-code results.
#
# Usage:
#   bash tools/fetch_reference_data.sh [DEST]
#
# DEST defaults to a sibling checkout named acwf-verification-scripts, which is
# where config.py looks by default (override with U14VE_ACWF_SCRIPTS).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-${ROOT}/../acwf-verification-scripts}"

if [[ -d "${DEST}/3-analyze/outputs" ]]; then
    echo "already present: ${DEST}"
    exit 0
fi

echo "cloning aiidateam/acwf-verification-scripts into ${DEST} (shallow, ~100 MB)"
git clone --depth 1 https://github.com/aiidateam/acwf-verification-scripts.git "${DEST}"
echo "done: set U14VE_ACWF_SCRIPTS=${DEST} if your layout differs"

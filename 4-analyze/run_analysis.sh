#!/usr/bin/env bash
#
# Run the whole analysis chain, in order, for the requested pseudopotentials.
#
# The four steps are ordered by dependency (the report reads the metrics JSONs, the
# metrics read the results JSONs, the results read AiiDA), and every step is given the
# same explicit list of pseudopotentials so that the report always contains the same
# columns as the metrics:
#
#   1. get_results.py          AiiDA -> results-<set>-quantum_espresso.json  (BM fits)
#   2. audit_standard.py       re-read the provenance of every SCF and verify the
#                              standard was applied (pseudopotential, cutoffs, k mesh,
#                              smearing, thresholds, one mesh per system)
#   3. compute_sssp_metrics.py Delta / nu / epsilon against the all-electron average
#   4. make_comparison_report.py  comparison_tables.md (+ ASCII EOS curves)
#   5. plot_ev_curves.py       one PNG per system with all curves
#
# Step 2 exits non-zero when it finds a deviation; that is a finding, not an
# infrastructure failure, so the chain reports it and continues by default
# (use --strict to stop instead).
#
# Usage:
#     bash 4-analyze/run_analysis.sh                 # sr fr
#     bash 4-analyze/run_analysis.sh sr fr rc1
#     bash 4-analyze/run_analysis.sh sr fr rc1 --strict
#
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

STRICT=0
PSEUDOS=()
for argument in "$@"; do
    case "${argument}" in
        --strict) STRICT=1 ;;
        -*) echo "unknown option: ${argument}" >&2; exit 2 ;;
        *) PSEUDOS+=("${argument}") ;;
    esac
done
if [ ${#PSEUDOS[@]} -eq 0 ]; then
    PSEUDOS=(sr fr)
fi

source "${CONDA_SH:-$HOME/install/miniconda3/etc/profile.d/conda.sh}"
conda activate aiida

echo "== pseudopotentials: ${PSEUDOS[*]}"
failures=0
for step in 4-analyze/get_results.py \
            4-analyze/audit_standard.py \
            4-analyze/compute_sssp_metrics.py \
            4-analyze/make_comparison_report.py \
            4-analyze/plot_ev_curves.py \
            tools/export_provenance_csv.py ; do
    echo
    echo "======================================================================"
    echo "== python ${step} --pseudos ${PSEUDOS[*]}"
    echo "======================================================================"
    python "${step}" --pseudos "${PSEUDOS[@]}"
    status=$?
    if [ "${status}" -ne 0 ]; then
        echo "!! ${step} exited with ${status}"
        failures=$(( failures + 1 ))
        if [ "${STRICT}" -eq 1 ]; then
            exit "${status}"
        fi
    fi
done

echo
echo "======================================================================"
echo "== outputs"
echo "======================================================================"
ls -1 "${PROJECT_ROOT}/4-analyze/outputs"/*.md "${PROJECT_ROOT}/4-analyze/outputs"/*.json 2>/dev/null
echo
if [ "${failures}" -ne 0 ]; then
    echo "Done, but ${failures} step(s) exited non-zero — read the output above."
    echo "A non-zero 4-analyze/audit_standard.py is a finding about the calculations,"
    echo "not a broken pipeline: an unfinished workchain is reported as a deviation."
    exit 1
fi
echo "Done. Report: 4-analyze/outputs/comparison_tables.md"

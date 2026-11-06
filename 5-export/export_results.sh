#!/usr/bin/env bash
#
# Export the AiiDA provenance of the verification runs.
#
# Creates one .aiida archive per pseudopotential set, containing the structure
# group, the EOS workchains and everything they depend on (calculations,
# pseudopotentials, computer/code descriptions).  The archives are self-contained
# and can be imported elsewhere with `verdi archive import`.
#
# Usage:
#     bash 5-export/export_results.sh              # both pseudopotentials
#     bash 5-export/export_results.sh sr           # only the scalar-relativistic one
#     bash 5-export/export_results.sh sr fr --spin-orbit
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_NAME="$(cat "${PROJECT_ROOT}/plugin_name.txt")"
EXPORT_DIR="${PROJECT_ROOT}/outputs"
mkdir -p "${EXPORT_DIR}"

SPIN_ORBIT=0
PSEUDOS=()
for argument in "$@"; do
    case "${argument}" in
        --spin-orbit) SPIN_ORBIT=1 ;;
        -*) echo "unknown option: ${argument}" >&2; exit 2 ;;
        *) PSEUDOS+=("${argument}") ;;
    esac
done
if [ ${#PSEUDOS[@]} -eq 0 ]; then
    PSEUDOS=(sr fr)
fi

for pseudo in "${PSEUDOS[@]}"; do
    variants=("u14ve-${pseudo}-verification-PBE-v1")
    if [ "${SPIN_ORBIT}" -eq 1 ] && [ "${pseudo}" = "fr" ]; then
        variants+=("u14ve-${pseudo}-soc-verification-PBE-v1")
    fi

    for set_name in "${variants[@]}"; do
        group="acwf-verification/${set_name}/workflows/${PLUGIN_NAME}"
        structures="acwf-verification/${set_name}/structures/${PLUGIN_NAME}"
        out="${EXPORT_DIR}/export-${set_name}.aiida"

        echo "== ${set_name}"
        echo "   workflows group : ${group}"
        echo "   structures group: ${structures}"
        verdi archive create "${out}" \
            --group "${group}" \
            --group "${structures}" \
            --description "u14ve-verification: ${set_name}"
        echo "   -> ${out}"
    done
done

echo
echo "Done. Import elsewhere with:  verdi archive import <file>.aiida"

#!/usr/bin/env python
"""Self-test of the analysis pipeline on published reference results.

Before spending CPU weeks on the real runs it is worth checking that the
post-processing is correct.  This script feeds the **published** Quantum
ESPRESSO/SSSP-1.3-precision EOS fits of uranium (shipped with
``acwf-verification-scripts``) through the very same metric code used for our own
runs and prints the resulting delta / nu / epsilon.

The expected magnitudes are known from the literature (uranium is a difficult
element for pseudopotentials):

    delta   <= ~2.5 meV/atom
    nu      <= ~0.5 %
    epsilon <= ~0.2

If this script reproduces numbers of that order, the reference data are being
read, the formula-unit normalisation is right and the metrics are sane.

Usage
-----

    python 4-analyze/selftest_metrics.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from common import util  # noqa: E402

PUBLISHED_RESULTS = {
    'unaries': 'results-unaries-verification-PBE-v1-quantum_espresso-SSSP-1.3-PBE-precision.json',
    'oxides': 'results-oxides-verification-PBE-v1-quantum_espresso-SSSP-1.3-PBE-precision.json',
}

# Any configured key works here: the self-test only uses the name to place a
# temporary results file. Hardcoding one broke the sibling project, which
# configures a single candidate under a different key.
SET_NAME = util.set_name(sorted(config.PSEUDOS)[0])


def load_metrics_module():
    path = PROJECT_ROOT / '4-analyze' / 'compute_sssp_metrics.py'
    spec = importlib.util.spec_from_file_location('compute_sssp_metrics', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_published_payload() -> dict:
    payload = {
        'script_version': '0.0.4',
        'set_name': 'published-QE-SSSP-1.3-precision',
        'uuid_mapping': {}, 'failed_wfs': [], 'missing_outputs': {}, 'completely_off': [],
        'eos_data': {}, 'stress_data': {}, 'BM_fit_data': {}, 'num_atoms_in_sim_cell': {},
    }
    for filename in PUBLISHED_RESULTS.values():
        path = config.REFERENCE_DATA_DIR / filename
        if not path.exists():
            raise SystemExit(f"ERROR: {path} not found — cannot run the self-test.")
        data = json.loads(path.read_text())
        for key, fit in data.get('BM_fit_data', {}).items():
            if not key.startswith('U-'):
                continue
            payload['BM_fit_data'][key] = fit
            payload['eos_data'][key] = data.get('eos_data', {}).get(key)
            payload['num_atoms_in_sim_cell'][key] = data.get('num_atoms_in_sim_cell', {}).get(key)
    return payload


def main() -> int:
    util.load_profile()

    metrics = load_metrics_module()
    reference = metrics.reference_fits()
    if not reference:
        print('ERROR: no all-electron reference data found.', file=sys.stderr)
        return 1

    payload = build_published_payload()
    if not payload['BM_fit_data']:
        print('ERROR: no published uranium results found.', file=sys.stderr)
        return 1

    print('=' * 78)
    print('Self-test: published QE/SSSP-1.3 results vs the all-electron average')
    print('=' * 78)

    with tempfile.TemporaryDirectory() as tmpdir:
        original = config.OUTPUTS_DIR
        config.OUTPUTS_DIR = Path(tmpdir)
        try:
            (Path(tmpdir) / f'results-{SET_NAME}-{util.PLUGIN_NAME}.json').write_text(
                json.dumps(payload, indent=2, sort_keys=True)
            )
            evaluated = metrics.evaluate(SET_NAME, reference)
        finally:
            config.OUTPUTS_DIR = original

    if not evaluated.get('systems'):
        print('ERROR: nothing evaluated — check the reference keys.', file=sys.stderr)
        return 1

    summary = metrics.summarise(evaluated)
    metrics.print_payload(evaluated, summary)

    print()
    limits = {'delta': 2.5, 'nu': 0.5, 'epsilon': 0.2}
    failures = []
    for metric, limit in limits.items():
        value = summary[metric]['max']
        ok = value <= limit
        print(f"  {metric:<8} max = {value:>8.4f}  (expected <= {limit})  {'OK' if ok else 'UNEXPECTED'}")
        if not ok:
            failures.append(metric)

    print()
    if failures:
        print(f"SELF-TEST FAILED for {failures}: the metric pipeline does not reproduce the")
        print('expected magnitude of the published results.')
        return 1
    print('SELF-TEST PASSED: the reference data, the formula-unit normalisation and the three')
    print('metrics behave as expected. Note that delta up to ~2 meV/atom for uranium is the')
    print('known accuracy of the SSSP precision library for this element — it is not a bug')
    print('of the pipeline.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

# Cutoff convergence report — 6p25-verification

Generated 2026-10-07 19:38 by `2-convergence/make_convergence_report.py` from the EOS workchains in AiiDA (no calculation was run for this report). Full diagnostics: the tables below are the long form of `convergence-report.md`.

## U, PBE, NC, 14 valence electrons, scalar-relativistic, from `ai_v1/6p25` (rcut 6s 1.50 / 7s 1.20 / 6p 1.60 / 6d 2.40 / 5f 1.30 bohr; 6 projectors: 6S, 7S, 6P, 6D, 5F and a second 6P at occupation 0 with reference energy -0.25 Ry)

| | |
|---|---|
| AiiDA set | `ai6p25v-6p25-verification-PBE-v1` |
| convergence groups | `acwf-verification/ai6p25v-6p25-verification-PBE-v1/convergence/...` |
| tested cutoffs (ecutwfc, dual) | 100/4, 110/4, 120/4, 150/4, 200/4, 250/4 |
| reference point | **200 Ry** (dual 4, ecutrho 800 Ry) |
| diagnostic systems | U-X/FCC, U-X/BCC, O2U-XO2, O3U2-X2O3 |
| criteria | ν ≤ 0.2 % (SSSP control protocol) · ε ≤ 0.01 |
| criterion judged below | epsilon |

| ecutwfc | ecutrho | ν(U-X/FCC) [%] | ε(U-X/FCC) | ν(U-X/BCC) [%] | ε(U-X/BCC) | ν(O2U-XO2) [%] | ε(O2U-XO2) | ν(O3U2-X2O3) [%] | ε(O3U2-X2O3) | ε verdict (cutoff) | EOS workchain PK / UUID |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 100 | 400 | 1.7522 | 0.15346 | 0.6596 | 0.19335 | 0.2133 | 0.12521 | 0.3824 | 0.23124 | cutoff NOT converged | U-X/FCC:495673 · U-X/BCC:499033 · O2U-XO2:495568 · O3U2-X2O3:499028 |
| 110 | 440 | 0.8399 | 0.29695 | 0.1969 | 0.06871 | 0.1403 | 0.04141 | 0.1355 | 0.03863 | cutoff NOT converged | U-X/FCC:487630 · U-X/BCC:499053 · O2U-XO2:487534 · O3U2-X2O3:499041 |
| 120 | 480 | 0.2153 | 0.07795 | 0.0612 | 0.01158 | 0.0769 | 0.02443 | 0.0899 | 0.03569 | cutoff NOT converged | U-X/FCC:495791 · U-X/BCC:499082 · O2U-XO2:495697 · O3U2-X2O3:499075 |
| 150 | 600 | 0.0130 | 0.00811 | 0.0053 | 0.00261 | 0.0167 | 0.00964 | 0.0207 | 0.00858 | cutoff-converged | U-X/FCC:487772 · U-X/BCC:499116 · O2U-XO2:487663 · O3U2-X2O3:499110 |
| 200 | 800 | 0.0000 | 0.00072 | 0.0000 | 0.00031 | 0.0000 | 0.00045 | 0.0000 | 0.00031 | cutoff-converged | U-X/FCC:487907 · U-X/BCC:499140 · O2U-XO2:487798 · O3U2-X2O3:499135 |
| 250 | 1000 | 0.0042 | 0.00204 | 0.0005 | 0.00017 | 0.0133 | 0.00355 | 0.0178 | 0.00623 | cutoff-converged | U-X/FCC:488049 · U-X/BCC:499171 · O2U-XO2:487934 · O3U2-X2O3:499162 |

### Did the SCFs converge? (a different question)

The verdicts above concern the **plane-wave cutoff**: whether the EOS still moves when more plane waves are added. They say nothing about the self-consistent field, which is a separate check (`conv_thr`, here `natoms × 1e-10 Ry`). For the same calculations:

| ecutwfc | standard `pw.x` SCFs | all reached `convergence_achieved` | worst `scf_error / conv_thr` | SCF steps |
|---|---|---|---|---|
| 100 | 28 | True | 0.482 | 10–15 |
| 110 | 28 | True | 0.487 | 10–15 |
| 120 | 28 | True | 0.470 | 11–15 |
| 150 | 28 | True | 0.500 | 10–16 |
| 200 | 28 | True | 0.441 | 10–15 |
| 250 | 28 | True | 0.464 | 10–16 |

A ratio below 1 means the final `estimated scf accuracy` was inside that calculation's own `conv_thr`. **Every SCF in every row above converged**, including the cutoffs whose *cutoff* verdict is "not converged".


### Fit quality per cutoff (read this before trusting a metric)

ν and ε are computed from *fitted* Birch-Murnaghan curves, so a fit that does not describe its seven points makes both metrics meaningless — even when every SCF converged. Two independent symptoms are shown below: the fitted B1 (the expected value for these systems is ≈4; a negative one is unphysical) and the RMS misfit of the fit expressed per atom, which is the number that matters for a per-atom metric.

| ecutwfc | system | B1 | BM residual [eV²] | RMS misfit [meV/atom] | flag |
|---|---|---|---|---|---|
| 100 | U-X/FCC | -2.407 | 1.03e-03 | 3.040 | **B1 unphysical; misfit large** |
| 100 | U-X/BCC | 0.533 | 1.85e-05 | 0.813 | **B1 unphysical; misfit large** |
| 100 | O2U-XO2 | 4.738 | 5.56e-05 | 0.235 | ok |
| 100 | O3U2-X2O3 | 5.058 | 1.05e-06 | 0.039 | ok |
| 110 | U-X/FCC | -0.143 | 1.17e-04 | 1.022 | **B1 unphysical; misfit large** |
| 110 | U-X/BCC | 6.137 | 6.59e-05 | 1.534 | **misfit large** |
| 110 | O2U-XO2 | 4.364 | 2.76e-05 | 0.166 | ok |
| 110 | O3U2-X2O3 | 3.491 | 1.83e-07 | 0.016 | ok |
| 120 | U-X/FCC | 5.682 | 9.57e-06 | 0.292 | ok |
| 120 | U-X/BCC | 6.031 | 3.74e-06 | 0.365 | **misfit large** |
| 120 | O2U-XO2 | 4.300 | 4.75e-06 | 0.069 | ok |
| 120 | O3U2-X2O3 | 4.880 | 1.74e-06 | 0.050 | ok |
| 150 | U-X/FCC | 4.427 | 7.74e-09 | 0.008 | ok |
| 150 | U-X/BCC | 5.047 | 5.38e-09 | 0.014 | ok |
| 150 | O2U-XO2 | 4.452 | 7.61e-06 | 0.087 | ok |
| 150 | O3U2-X2O3 | 4.440 | 1.05e-08 | 0.004 | ok |
| 200 | U-X/FCC | 4.431 | 1.61e-09 | 0.004 | ok |
| 200 | U-X/BCC | 5.033 | 4.47e-09 | 0.013 | ok |
| 200 | O2U-XO2 | 4.259 | 1.14e-06 | 0.034 | ok |
| 200 | O3U2-X2O3 | 4.597 | 2.72e-06 | 0.062 | ok |
| 250 | U-X/FCC | 4.442 | 2.64e-09 | 0.005 | ok |
| 250 | U-X/BCC | 5.030 | 1.23e-08 | 0.021 | ok |
| 250 | O2U-XO2 | 4.413 | 3.01e-09 | 0.002 | ok |
| 250 | O3U2-X2O3 | 4.436 | 1.26e-07 | 0.013 | ok |

Flagged rows mean: do **not** quote that point's ν/ε as a converged-basis statement. This is what a non-monotonic distance in the table above looks like from the inside — the metric is fine, the fit underneath it is not.

### Recommendation

* **nu <= 0.2 %: 150 Ry** (worst system 0.020725 %, margin 9.7x).
* **epsilon <= 0.01: 150 Ry** (worst system 0.0096441, margin 1.0x).

**Residual movement at the top of the scan** (200 → 250 Ry): U-X/FCC: |Δν| = 0.0042 %, |Δε| = 0.00132 · U-X/BCC: |Δν| = 0.0005 %, |Δε| = 0.00015 · O2U-XO2: |Δν| = 0.0133 %, |Δε| = 0.00311 · O3U2-X2O3: |Δν| = 0.0178 %, |Δε| = 0.00592. This is the part of the scan that the reference cannot see; if it is not comfortably below the tolerances, the reference is too low.

### Distance between neighbouring cutoffs (reference-free)

The `Δ` above is a difference of two distances to the same reference. This table is the purer quantity: the EOS fitted at one cutoff compared directly with the EOS fitted at the next one. If a step is well below the tolerance, adding that much basis changed nothing observable.

| step [Ry] | ν(U-X/FCC) [%] | ε(U-X/FCC) | ν(U-X/BCC) [%] | ε(U-X/BCC) | ν(O2U-XO2) [%] | ε(O2U-XO2) | ν(O3U2-X2O3) [%] | ε(O3U2-X2O3) | worst ν | worst ε |
|---|---|---|---|---|---|---|---|---|---|---|
| 100 → 110 | 0.5971 | 0.19580 | 0.7545 | 0.19474 | 0.2391 | 0.12436 | 0.4708 | 0.25978 | 0.7545 | 0.25978 |
| 110 → 120 | 0.9828 | 0.36426 | 0.1814 | 0.06296 | 0.2169 | 0.06523 | 0.2212 | 0.07365 | 0.9828 | 0.36426 |
| 120 → 150 | 0.2218 | 0.08414 | 0.0572 | 0.01113 | 0.0660 | 0.01909 | 0.1055 | 0.04326 | 0.2218 | 0.08414 |
| 150 → 200 | 0.0130 | 0.00811 | 0.0053 | 0.00261 | 0.0167 | 0.00964 | 0.0207 | 0.00858 | 0.0207 | 0.00964 |
| 200 → 250 | 0.0042 | 0.00205 | 0.0005 | 0.00018 | 0.0133 | 0.00356 | 0.0178 | 0.00624 | 0.0178 | 0.00624 |

Read together with the `Δ` columns: a small `Δ` on a row whose neighbouring-step distance is also small means the scan has genuinely saturated there; a small `Δ` with a large neighbouring-step distance means the two errors happen to cancel and nothing is settled yet.

### Sensitivity to the choice of the reference point

The scan can only recommend a cutoff for a reference *above* it, so this table shows what every possible reference would give. A reference that is too low either yields no converged point or a misleadingly low one.

| reference [Ry] | smallest converged: ν ≤ 0.2 % | smallest converged: ε ≤ 0.01 |
|---|---|---|
| 100 | — | — |
| 110 | — | — |
| 120 | — | — |
| 150 | — | — |
| 200 | 150 Ry | 150 Ry |
| 250 | 150 Ry | 200 Ry |

### Non-monotonic distances (treat with care)

A distance that grows when the cutoff grows means the measurement is dominated by fit noise rather than by a systematic cutoff error — check the fit-quality table above for the point in question:

* ε(110 Ry) = 0.29695 > 0.23124 at 100 Ry
* ε(250 Ry) = 0.0062304 > 0.00072178 at 200 Ry

### Notes on this measurement

* **ε has a numerical floor.** The official implementation returns ≈5×10⁻⁴ for two *identical* EOS fits (it prints `eps2 = negative due to numerical error probably` while doing so), so the reference row shows ~5×10⁻⁴ rather than 0. Values within a few times that floor are at the resolution limit of the metric.
* **ε is much stricter than ν.** A perturbation test gives ε ≈ 0.01 for an equilibrium-volume error of only ~0.015 %, while ν ≤ 0.2 % allows roughly 0.2 % — about an order of magnitude looser on V₀.
* **The reference must be far enough above the recommended cutoff.** With a reference that is only marginally converged the distances saturate at the reference's own residual, and the recommendation drifts upwards; the sensitivity table above shows how much.
* **"cutoff NOT converged" is not a failed calculation.** It means the EOS at that cutoff still differs from the reference EOS by more than the tolerance, i.e. the plane-wave basis is not complete enough yet — the SCF itself converged (see the SCF table above). The opposite confusion is also possible: an SCF that hits its iteration limit (`electron_maxstep`) is reported by the audit (`4-analyze/audit_standard.py`) and by the exit status, not by this table.
* Every row can be traced to its AiiDA nodes with `verdi process show <PK>`; the same PKs appear in `4-analyze/outputs/provenance-convergence.csv`.


### Reproduction

```bash
python 2-convergence/run_cutoff_convergence.py --pseudos 6p25 \
       --cutoffs 100 110 120 150 200 250 --configurations X/FCC X/BCC XO2 X2O3 --run --max-memory-gb 100
python 2-convergence/select_cutoffs.py --pseudos 6p25
python 2-convergence/make_convergence_report.py --pseudos 6p25 --reference-ecut 200
```

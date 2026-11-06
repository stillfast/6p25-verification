# Cutoff convergence report — 6p25-verification

Generated 2026-10-07 19:38 by `2-convergence/make_convergence_report.py` from the EOS workchains in AiiDA (no calculation was run for this report).

## U, PBE, NC, 14 valence electrons, scalar-relativistic, from `ai_v1/6p25` (rcut 6s 1.50 / 7s 1.20 / 6p 1.60 / 6d 2.40 / 5f 1.30 bohr; 6 projectors: 6S, 7S, 6P, 6D, 5F and a second 6P at occupation 0 with reference energy -0.25 Ry)

Scan of `ai6p25v-6p25-verification-PBE-v1` over 100/4, 110/4, 120/4, 150/4, 200/4, 250/4 Ry (ecutwfc/dual); every row is compared with the reference point **200 Ry**; criterion ε ≤ 0.01. ν in %, ε dimensionless. Δ = this row minus the previous (lower-cutoff) row.

### U-X/FCC

| ecutwfc | ecutrho | ν(U-X/FCC) | Δν(U-X/FCC) | ε(U-X/FCC) | Δε(U-X/FCC) |
|---|---|---|---|---|---|
| 100 | 400 | 1.7522 | — | 0.15346 | — |
| 110 | 440 | 0.8399 | -0.9123 | 0.29695 | +0.14349 |
| 120 | 480 | 0.2153 | -0.6245 | 0.07795 | -0.21899 |
| 150 | 600 | 0.0130 | -0.2024 | 0.00811 | -0.06984 |
| 200 | 800 | 0.0000 | -0.0130 | 0.00072 | -0.00739 |
| 250 | 1000 | 0.0042 | +0.0042 | 0.00204 | +0.00132 |

### O2U-XO2

| ecutwfc | ecutrho | ν(O2U-XO2) | Δν(O2U-XO2) | ε(O2U-XO2) | Δε(O2U-XO2) |
|---|---|---|---|---|---|
| 100 | 400 | 0.2133 | — | 0.12521 | — |
| 110 | 440 | 0.1403 | -0.0729 | 0.04141 | -0.08381 |
| 120 | 480 | 0.0769 | -0.0635 | 0.02443 | -0.01698 |
| 150 | 600 | 0.0167 | -0.0602 | 0.00964 | -0.01478 |
| 200 | 800 | 0.0000 | -0.0167 | 0.00045 | -0.00920 |
| 250 | 1000 | 0.0133 | +0.0133 | 0.00355 | +0.00311 |

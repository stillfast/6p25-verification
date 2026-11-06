# Cutoff convergence report — 6p25-verification

Generated 2026-10-07 19:38 by `2-convergence/make_convergence_report.py` from the EOS workchains in AiiDA (no calculation was run for this report).

## U, PBE, NC, 14 valence electrons, scalar-relativistic, from `ai_v1/6p25` (rcut 6s 1.50 / 7s 1.20 / 6p 1.60 / 6d 2.40 / 5f 1.30 bohr; 6 projectors: 6S, 7S, 6P, 6D, 5F and a second 6P at occupation 0 with reference energy -0.25 Ry)

Scan of `ai6p25v-6p25-verification-PBE-v1` over 100/4, 110/4, 120/4, 150/4, 200/4, 250/4 Ry (ecutwfc/dual); every row is compared with the reference point **200 Ry**; criterion ε ≤ 0.01. ν in %, ε dimensionless. Δ = this row minus the previous (lower-cutoff) row.

### U-X/BCC

| ecutwfc | ecutrho | ν(U-X/BCC) | Δν(U-X/BCC) | ε(U-X/BCC) | Δε(U-X/BCC) |
|---|---|---|---|---|---|
| 100 | 400 | 0.6596 | — | 0.19335 | — |
| 110 | 440 | 0.1969 | -0.4627 | 0.06871 | -0.12464 |
| 120 | 480 | 0.0612 | -0.1358 | 0.01158 | -0.05713 |
| 150 | 600 | 0.0053 | -0.0559 | 0.00261 | -0.00897 |
| 200 | 800 | 0.0000 | -0.0053 | 0.00031 | -0.00230 |
| 250 | 1000 | 0.0005 | +0.0005 | 0.00017 | -0.00015 |

### O3U2-X2O3

| ecutwfc | ecutrho | ν(O3U2-X2O3) | Δν(O3U2-X2O3) | ε(O3U2-X2O3) | Δε(O3U2-X2O3) |
|---|---|---|---|---|---|
| 100 | 400 | 0.3824 | — | 0.23124 | — |
| 110 | 440 | 0.1355 | -0.2470 | 0.03863 | -0.19261 |
| 120 | 480 | 0.0899 | -0.0456 | 0.03569 | -0.00294 |
| 150 | 600 | 0.0207 | -0.0692 | 0.00858 | -0.02712 |
| 200 | 800 | 0.0000 | -0.0207 | 0.00031 | -0.00827 |
| 250 | 1000 | 0.0178 | +0.0178 | 0.00623 | +0.00592 |

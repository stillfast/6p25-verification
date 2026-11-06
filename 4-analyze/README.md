# 4-analyze — 结果提取与指标计算

按顺序运行即可。

## `selftest_metrics.py`（先跑这个）

把**已发表**的 `quantum_espresso + SSSP-1.3-PBE-precision` 的 U 结果喂进本项目的指标代码，
验证：参考数据读取、每化学式单元 / 每原子的归一化、三个指标的量级。

```bash
python 4-analyze/selftest_metrics.py
```

自检通过的标准是 Δ_max ≤ 2.5 meV/atom、ν_max ≤ 0.5 %、ε_max ≤ 0.2
（实测 2.17 / 0.25 / 0.16，即铀在 SSSP precision 库下的已知精度水平）。
这一步不需要任何计算，几秒钟。

## `get_results.py`

遍历每个 set 的 workflows 组，取每个 `EquationOfStateWorkChain` 的
体积-能量数据点，用官方 `eosfit_31_adapted.BM` 拟合 Birch-Murnaghan，
输出与 `acwf-verification-scripts` **同格式**的文件：

```
4-analyze/outputs/results-<set>-quantum_espresso.json
4-analyze/outputs/warnings-<set>-quantum_espresso.txt
```

失败的 workchain 也会尽量抢救：只要 80 % 以上的体积算完就仍然拟合。

```bash
python 4-analyze/get_results.py
python 4-analyze/get_results.py --pseudos sr --include-spin-orbit
```

## `compute_sssp_metrics.py` ★

对每个体系计算三个 ACWF/SSSP 指标（实现直接拷贝自官方
`quantities_for_comparison.py`），参考数据是 ACWF 论文发布的全电子平均值：

* **Δ [meV/atom]**：能量 RMS 差（±6 % 体积窗口）
* **ν [%]**：V₀、B₀、B₁ 的加权相对偏差
* **ε**：两条 EOS 曲线间的归一化面积

同时给出：单质 / 氧化物分别的最大值与判定（PASS / acceptable / FAIL，
阈值见 `common/standard.py::CRITERIA`），以及

* 两个候选赝势**互相对比**（`sr` vs `fr`）——两者除相对论处理外构造完全相同，
  所以这组数字直接量化"全相对论 vs 标量相对论"的差异；
* `--compare-set FILE`：与任意已发表/历史 results JSON 对比。

输出：

```
4-analyze/outputs/metrics-<set>.json
4-analyze/outputs/metrics-<set>.md
```

```bash
python 4-analyze/compute_sssp_metrics.py
python 4-analyze/compute_sssp_metrics.py --include-spin-orbit
python 4-analyze/compute_sssp_metrics.py --compare-set \
  ../acwf-verification-scripts/acwf_paper_plots/code-data/results-unaries-verification-PBE-v1-quantum_espresso-SSSP-1.3-PBE-precision.json
```

## `plot_ev_curves.py`

每个体系一张 E-V 图（按化学式单元归一化，和官方图一致）：
数据点 + BM 拟合曲线，请求的候选赝势叠加，并画出全电子参考曲线。
图例里的 V₀ / B₀ / Δ 与 `metrics-*.md` **同源同值**（Δ 由 `common.eosdata.delta_per_atom`
计算，两边都用每原子体积，不再多除一次化学式单元原子数）。

```bash
python 4-analyze/plot_ev_curves.py
python 4-analyze/plot_ev_curves.py --configurations X/BCC XO2 --output 4-analyze/outputs/plots
```

`--reference-codes` 会把已发表的其他代码（`config.REFERENCE_CODES`：`qe-sssp`、`vasp`、
`fleur`、`wien2k`、`castep`，取自官方 `acwf-verification-scripts/3-analyze/outputs`）
当作普通曲线画进去——7 个 EOS 点 + BM 拟合，Δ 同样对全电子平均计算。
其中 `qe-sssp` 就是 SSSP precision 库用 **Quantum ESPRESSO** 算的官方结果
（`results-{unaries,oxides}-verification-PBE-v1-Quantum ESPRESSO@PW|SSSP-prec-v1.3.json`），
和本项目同一个代码，可比性最强。
`--no-ae-average` 可以只留代码对比。只画某一个赝势：

```bash
python 4-analyze/plot_ev_curves.py --pseudos v13 --reference-codes qe-sssp vasp castep \
  --output 4-analyze/outputs/plots-v13-refs
```

每个体系的横轴窗口由所有被画的曲线共同决定（已发表算例的初始结构与我们相差最多
0.7 %，例如 U-X/SC），所以不会出现曲线被裁掉的情况；曲线（含全电子参考）到 4 条以上时
图例自动改成两列，并在顶部预留出它占的那一条空白带，不会压住曲线。
加 `--ascii` 还会把同样的曲线打成文本表格，便于在没有图像查看器的终端里核对。

## 判据与归一化的两点说明

1. 阈值是可配置的（`common/standard.py::CRITERIA`）。默认 PASS 值取常被引用的
   SSSP precision 判据：Δ ≤ 1 meV/atom、ν ≤ 0.5 %、ε ≤ 5 %。正式汇报前请核对
   SSSP 论文 Table 2（*npj Comput. Mater.* **4**, 72 (2018)）。
2. 官方 `generate_histos.py` 输出的 Δ 是"每化学式单元"；这里统一换算成 **meV/atom**
   （除以化学式单元原子数），才与 SSSP 判据可比。ν、ε 是对比量，与归一化无关。

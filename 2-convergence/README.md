# 2-convergence — 截断收敛（SSSP control 协议）

两个候选赝势的 UPF 头里都没有推荐截断（`Suggested minimum cutoff ... 0. Ry`），
所以必须先自己扫一遍，做法与 SSSP 官方验证流程一致
（`aiida-sssp-workflow` 的 `protocol/control.yml` 与 `control_U.yml`）：

* 固定 **dual**（`ecutrho = dual × ecutwfc`，NC 默认 dual = 4）扫 `ecutwfc`；
  因为 U 有 f 通道，扫描从 50 Ry 起；
* 在最大 `ecutwfc` 处再扫 dual（SSSP 的 `nc_dual_scan`）。

每个截断点都在一小撮代表性结构上（默认 `X/BCC` + `XO2`）算一条 **7 点 EOS**。

```bash
# 先看清单（dry run）
python 2-convergence/run_cutoff_convergence.py --pseudos sr fr

# 提交扫描
python 2-convergence/run_cutoff_convergence.py --pseudos sr fr --scan quick --run
#   预设：test [60,100,200] / quick [50,60,75,100,150,200] / standard [50..200 每 5 Ry]

# 附加 dual 扫描（在 200 Ry 处）
python 2-convergence/run_cutoff_convergence.py --pseudos sr --duals 3 4 6 8 --run

# 自定义
python 2-convergence/run_cutoff_convergence.py --pseudos sr --cutoffs 60 80 100 120 150 --run
```

每组结果放在自己的 AiiDA 组里，标签自带参数，例如：

```
acwf-verification/u14ve-sr-verification-PBE-v1/convergence/quantum_espresso/ecut-100-dual-4
```

## `select_cutoffs.py`

等某个截断点的 EOS 跑完后（可以先选一部分点跑），用**与正式分析完全相同的
Birch-Murnaghan 拟合**比较各截断点的 EOS 与参考点（最大 `ecutwfc`，其中 dual 最大者）的
EOS，判据取 SSSP `criteria.yml` 中 `standard` 组的 `eos: bounds = [0.0, 0.2]`，
即 ν 型距离（权重 B₀ 1/20、B₁ 1/400，单位 %）≤ 0.2。

推荐截断 = **所有扫描结构都满足判据的最小扫描点**。

```bash
python 2-convergence/select_cutoffs.py --pseudos sr fr
python 2-convergence/select_cutoffs.py --pseudos sr --tolerance 0.1
```

输出 `2-convergence/cutoffs.json`，例如：

```json
{
  "sr": {"U": {"ecutwfc": 100.0, "ecutrho": 400.0, "dual": 4.0, "converged": true,
                "nu_percent": {"U-X/BCC": 0.03, "O2U-XO2": 0.11}},
         "O": {"ecutwfc": 60.0, "ecutrho": 480.0},
         "_meta": {"reference_point": {...}, "tolerance_percent": 0.2}},
  "fr": {...},
  "_metadata": {...}
}
```

`3-submit/launch_calculations_qe.py` 会自动读取它；没有这个文件时回退到
`config.py` 里 `PSEUDOS[*]['default_cutoffs']`（当前 120/480 Ry，是**待收敛确认的暂定值**）。

注意：混合 U/O 体系的有效截断取两者最大值，所以 U 的截断若低于 60 Ry，
氧化物体系仍会被 O 的 60 Ry 顶上去；这一点在表格里会如实反映。

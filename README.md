# 6p25-verification

**对象**：`U.pbe-n-nc.UPF` —— ld1.x 生成的铀 **14 价电子**模守恒赝势，**随本仓库分发**
（仓库根目录，md5 `024f9a435d4b4c50e9267d14ff369f4e`；原始生成目录为 `uranium-ppgen/ai_v1/6p25/`）。
**范围**：**全部 10 个 ACWF 体系**（4 单质 + 6 氧化物），每个体系一条 7 点 EOS，
ACWF `verification-PBE-v1` 标准。

## 与已验证的 v13 的关系（重要）

这份文件**数值上与已经验证过的 `v13` 是同一个赝势**：

| 文件 | md5 | 关系 |
|---|---|---|
| `ai_v1/6p25/U.pbe-n-nc.UPF`（本项目） | `024f9a43…` | 与下面那份**只差 `<PP_INFO>` 里一行回显** |
| `v13/rd/runs/rlderiv/rlderiv_5p0/U.pbe-n-nc.UPF`（v13 验证用的那份） | `3df70b81…` | 去掉 `PP_INFO` 后与上面**逐字节相同** |
| `v13/pp/U.pbe-n-nc.UPF` | `024f9a43…` | 与 6p25 顶层这份完全相同 |

唯一的差异是 `nld = 4`（6p25 那份）与 `nld = 6`（v13 那份）——`PP_INFO` 是 ld1.x 回显的
生成输入，**QE 不读它**，赝势数据（PP_LOCAL/PP_NONLOCAL/PP_BETA/PP_DIJ/PP_RHOATOM…）
两份完全一致。所以本项目的全量验证同时也是对 `u14ve-verification` 里 `v13` 结果的
**独立复现**（不同文件、不同 AiiDA set、重新上机跑）。

注意另一个容易混淆的邻居：同一个 `6p25/` 目录里还有 `6p25/rc_best/U.pbe-n-nc.UPF`
（md5 `c61b6ebf…`），那是**不同的**赝势，已经由 `../rcbest-verification`
（SET_PREFIX `ai6p25`）验证过。本项目用 `ai6p25v` 前缀，两套数据不会混。

## 赝势参数

| 项 | 值 |
|---|---|
| 元素 / 类型 / 相对论 | U / NC（UPF v2） / **scalar** |
| 价电子 | 14（6s²6p⁶5f³6d¹7s²） |
| XC / NLCC | PBE / 有 |
| 半径 [bohr] | 6S 1.50 \| 7S 1.20 \| 6P 1.60 \| 6D 2.40 \| 5F 1.30 \| 第二个 6P（occ 0, −0.25 Ry） |
| 投影子 | 6 |
| `ld1.test` 最差 | 5F 0.08 mRy |
| 条件数 | `cond(S) = 9.66×10⁴`、`cond(D) = 797` |
| UPF 头推荐截断 | 无（`wfc_cutoff = 0`），必须自己扫 |

## 运行前提（自包含程度）

**随仓库提供**：全部脚本与配置、两个赝势（`U.pbe-n-nc.UPF` 研究对象 + `O_ONCV_PBE-1.0.upf`）、
ACWF 十体系结构归档（`data/structures/`）、全电子平均参考数据（`data/reference/`，算 Δ/ν/ε 用）、
`requirements.txt` / `pyproject.toml` / `environment.yml`、`2-convergence/` 的扫描报告与 `cutoffs.json`。

**仍需自备**（仓库无法分发）：

| 依赖 | 用途 | 获取方式 |
|---|---|---|
| AiiDA profile + `pw.x` code（默认 `qe@yeesuan`） | 所有计算 | `verdi quicksetup` / 现有 profile；改 `config.py` 的 `CODE_LABEL` |
| 已发表 code 的参考结果（`3-analyze/outputs/*.json`） | 4-analyze 的跨 code 对比 | `bash tools/fetch_reference_data.sh`，或设 `U14VE_ACWF_SCRIPTS` |
| 集群/队列 | 真实提交 | 改 `config.py` 的 `COMPUTER_OPTIONS` |

**最小可运行路径**：

```bash
bash tools/fetch_reference_data.sh      # 只影响最后的跨 code 对比，可后补
python 1-preliminary/import_structures.py # 导入 data/structures/ 的结构归档（一次性）
make verify                               # 之后按 Makefile 的 target 走
```

两个赝势都已就位，只跑 4 个 U 单质（`X/SC`、`X/BCC`、`X/FCC`、`X/Diamond`）无需额外下载。

**许可**：`O_ONCV_PBE-1.0.upf` 是第三方 SG15/ONCV 赝势（CC BY-SA 4.0，M. Schlipf & F. Gygi），
详见 `THIRD_PARTY_NOTICES.md`；其余代码为 MIT。

## 标准与截断

* **标准**：ACWF `verification-PBE-v1`（k 距离 0.06 Å⁻¹、7 点 EOS ±6 %、
  `conv_thr = natoms × 1e-10 Ry`、`fd` smearing 0.0045 Ry、`relax_type = NONE`），QE `pw.x`。
* **截断**：先按 SSSP control 协议扫 **110 / 150 / 200 / 250 Ry（dual 4）**
  （参考点 250 Ry，判据 ν ≤ 0.2 %），再以 `cutoffs.json` 的推荐值跑 10 体系生产。
  v13 对同一赝势数据的推荐值是 150/600 Ry，本次扫描独立复核。

## 执行命令

```bash
cd 6p25-verification            # 克隆后的仓库目录
python 1-preliminary/import_structures.py
python 1-preliminary/install_pseudos.py
python 1-preliminary/create_starting_subgroups.py    # 本项目默认建全部 10 个结构
python 1-preliminary/verify_setup.py
python 2-convergence/run_cutoff_convergence.py --pseudos 6p25 \
    --cutoffs 110 150 200 250 --max-memory-gb 100 --run
python 2-convergence/select_cutoffs.py --pseudos 6p25
python 3-submit/launch_calculations_qe.py --pseudos 6p25 --max-memory-gb 100 --run
bash 4-analyze/run_analysis.sh 6p25
```

或者用 `make`（同一个流程的封装，`RUN=1` 才会真的提交）：

```bash
make structures pseudos subgroups verify   # 准备
make convergence RUN=1                     # 截断扫描
make cutoffs                               # 选截断
make submit RUN=1                          # 生产
make analyze                               # 分析
```

规模：扫描 8 个 EOS（56 SCF）+ 生产 10 个 EOS（70 SCF），合计 126 个标准 SCF
（另有同数量的、被丢弃的 `base_init_relax` 预弛豫 SCF，因为可选补丁未打）。

## 执行结果（2026-10-06）：与 v13 **逐位一致**

完整报告由 `4-analyze/run_analysis.sh` 生成在 **`4-analyze/outputs/6P25-verification.md`**（产物默认不入库）；扫描表归档在
`2-convergence/cutoff-scan.log`。

* **截断**：扫描 110/150/200/250 Ry（参考 250，结构 X/FCC + XO₂），
  ν(110) = 0.1307 / 0.8418 %（**未收敛**）、ν(150) = 0.0222 / 0.0169 % →
  **推荐 150 / 600 Ry（dual 4）**，与 v13 同一结论。
* **生产**：10 个 EOS workchain 全部 exit 0（80 分钟），
  `audit_standard.py` → **AUDIT PASSED**（70 个合规 SCF，无偏差）。
* **原始曲线**：10/10 体系极小值都在 ±6 % 窗口内的第 4/7 点，能量跨度 32.0–54.9 meV/atom。
* **指标（150 Ry，对全电子平均）**：Δ 最大 3.130（U-X/SC，FAIL）、均值 **1.002**；
  ν 最大 0.449 %（PASS）、均值 0.160 %；ε 最大 0.277（U-X/SC，FAIL）、均值 0.098。
  氧化物平均 Δ = **0.627**（优于 QE-SSSP 0.896、VASP 1.301、CASTEP 1.979）；
  单质平均 1.564（落后于 QE-SSSP 0.805、VASP 0.562）。
* **与 `u14ve-verification` 的 v13 结果对比：每个体系的 Δ/ν/ε 与三项汇总统计
  （最大/均值）全部浮点逐位相同** —— 这既是"两份文件数值上是同一赝势"的实证，
  也是该结果的一次独立复现（不同文件字节、不同 AiiDA set、重新上机跑）。

## 目录内容

```
config.py                   赝势/标准/范围等全部可调参数
common/                     ACWF 标准、Δ/ν/ε 官方实现、BM 拟合、EOS 提取
1-preliminary/              上传赝势、建族、建结构子组、检查 setup
2-convergence/              SSSP 协议截断扫描 → cutoffs.json
3-submit/                   按标准提交 EOS（默认全部 10 体系）
4-analyze/                  取结果、审计、Δ/ν/ε、对比报告（含已发表代码）、E-V 图
5-export/  tools/           provenance 导出、UPF 前置检查等
```

AiiDA set：`ai6p25v-6p25-verification-PBE-v1`。

**读结果的顺序**（本工作区的教训）：先看原始曲线的极小值是否落在 ±6 % 窗口内、
窗口内能量跨度是否在 30–60 meV/atom（`completely_off` 字段与逐点 ΔE 表），
再看 Δ/ν/ε；只看 ν 和拟合值会被外推骗过。

---

## 追加功能 1：结果核查用的 provenance CSV（PK / UUID）

`tools/export_provenance_csv.py` 把每个 process 节点的 **PK 与 UUID** 导出成 CSV，覆盖
**convergence 与 submit 两部分**，并已接到 `4-analyze/run_analysis.sh` 的最后一步
（每次跑分析都会重出）。产物在 `4-analyze/outputs/`：

| 文件 | 内容 |
|---|---|
| `provenance-convergence.csv` | 截断扫描的每个截断点 × 每个体系 |
| `provenance-submit.csv` | 生产提交的部分 |
| `provenance-all.csv` | 两者合并 |

列：`part, set, group, ecutwfc, dual, system, level, label, pk, uuid, parent_pk, state,
exit_status, ctime, mtime, remote_workdir, pseudos, kpoints`。

调用链 ACWF 是四层
（`EquationOfStateWorkChain → QuantumEspressoCommonRelaxWorkChain → PwRelaxWorkChain →
PwBaseWorkChain → PwCalculation`），工具做**递归遍历**而不是写死层级，所以每一层都在表里；
`level` 给出深度（`eos`、`work_chain_L1..L3`、`calculation_L1..L4`），`label` 给出类名，
`parent_pk` 让调用树可以只看 CSV 就重建。`pw.x` 行还带**该次计算实际用的赝势文件名与 k 网格**
——这是核查"这次算的是不是我要的赝势"最快的一步。

```bash
python tools/export_provenance_csv.py --pseudos 6p25             # 全部（含被 kill 的节点）
python tools/export_provenance_csv.py --pseudos 6p25 --only-ok   # 只保留正常结束的 workchain
grep 'O2U-XO2' 4-analyze/outputs/provenance-convergence.csv | grep ',eos,'
verdi process show <pk>                                        # 拿 PK 追任意一层
```

规模：本项目 1296 行（18 个 EOS workchain = convergence 4 截断 × 2 体系 + 生产 10），
其中 252 行是 `pw.x` 计算。

## 追加功能 2：以 ε 为判据的截断收敛（参考 200 Ry，阈值 0.01）

`select_cutoffs.py` 新增三个选项：

* `--criterion {nu,epsilon}` —— 用哪个距离判定收敛（`nu` 仍是 SSSP control 协议的默认）；
* `--tolerance` —— 判据阈值（`nu` 默认 0.2 %，`epsilon` 默认 0.01）；
* `--reference-ecut` —— 指定参考截断（本次按要求取 **200 Ry**）。

表格现在**同时打印 ν 与 ε**，判定用所选判据；JSON 里记录
`criterion / tolerance / reference_point` 以及两个指标的逐点值。
`common/eosdata.py` 增加了 `epsilon_between_fits()`（官方 `quantities_for_comparison.epsilon`
的实现；已验证 ε 与"按胞/按化学式单位"两种体积约定无关）。

两点必须知道：

* **ε 有数值本底**：官方实现即使对两条完全相同的曲线也只给到 ~5×10⁻⁴（它自己会打印
  `eps2 = negative due to numerical error probably`），所以参考点显示的是 5e-4 而不是 0；
  用 0.01 判据时可直接忽略。
* **ε 比 ν 严得多**：扰动测试表明 ε = 0.01 约对应 **V₀ 偏差 0.015 %**，而 ν ≤ 0.2 %
  允许约 0.2 % 的 V₀ 误差——即该判据大致比 SSSP 的 ν 判据紧一个量级。

### 结果（100/120/150/200 网格，参考 200 Ry，阈値 0.01）

| ecutwfc | ν(XO₂) | ν(X/FCC) | ε(XO₂) | ε(X/FCC) | ε 判据 |
|---|---|---|---|---|---|
| 100 | 0.2133 % | 1.7522 % | 0.12521 | 0.15346 | 未收敛 |
| 110 | 0.1403 % | 0.8399 % | 0.04141 | 0.29695 | 未收敛 |
| 120 | 0.0769 % | 0.2153 % | 0.02443 | 0.07795 | 未收敛 |
| **150** | 0.0167 % | 0.0130 % | **0.00964** | **0.00811** | **收敛** |
| 200（参考） | 0 | 0 | 0.00045 | 0.00072 | — |
| 250 | 0.0133 % | 0.0042 % | 0.00355 | 0.00204 | 收敛 |

**结论：ε < 0.01 判据给出 150 Ry（=600 Ry dual 4），与 ν 判据一致**，但这个判据比 ν 严
一个量级、结论更硬：120 Ry 明确不收敛（ε = 0.024/0.078），150 Ry 通过（余量较薄：0.0096 vs 0.01）。

记录：`2-convergence/cutoff-scan-epsilon.log`（控制台全表）、
`2-convergence/cutoffs-epsilon.json`（供 launcher 读取；**没有**覆盖原来的 ν 判据
`cutoffs.json`，两套并存便于对照）。

复现：

```bash
python 2-convergence/select_cutoffs.py --pseudos 6p25 --criterion epsilon \
    --reference-ecut 200 --tolerance 0.01 --output 2-convergence/cutoffs-epsilon.json
```

### 收敛扫描的 markdown 报告

`2-convergence/make_convergence_report.py` 把同一个扫描数据渲染成 markdown（不跑任何计算），
每行都带该点的 EOS workchain **PK/UUID**，并额外给出"参考点灵敏度表"（换参考截断会推荐什么）、
可选的两两距离矩阵、以及非单调距离的告警：

```bash
python 2-convergence/make_convergence_report.py --pseudos <KEY>            # 参考=最大的扫描点
python 2-convergence/make_convergence_report.py --pseudos <KEY> --reference-ecut 200 --matrix
```

产物：`2-convergence/convergence-report.md`（短表：每个诊断体系一张表，列为 `ecutwfc | ecutrho | ν | Δν | ε | Δε`，Δ = 本行减上一行更低截断点的数值）和 `2-convergence/convergence-report-full.md`（长表：相邻截断点距离、参考点敏感性、SCF 收敛检查、BM 拟合质量、PK/UUID）。

`--systems` 只过滤短表、`--full-systems` 控制长表覆盖哪些体系，因此可以做到"主报告只放当前这组
结构，长表仍然保留全部体系"。

### 第二组诊断结构（`X/BCC` + `X2O3`）

第一组结构（`X/FCC` + `XO2`）算完后，同一批截断点在**另一组结构**上又算了一遍，用来独立复核
150 Ry 这个选择（金属从 FCC 换成 BCC，氧化物从 UO₂ 换成 U₂O₃；共 12 个 EOS workchain，
全部成功、0 失败）：

```bash
python 2-convergence/run_cutoff_convergence.py --pseudos 6p25 \
    --cutoffs 100 110 120 150 200 250 --configurations X/BCC X2O3 \
    --max-memory-gb 150 --run
```

> **坑**：controller 用**组成员资格**判断某结构在某截断点是否算过，不看进程状态。当年误提交
> 留下的 `killed` 节点仍留在 `convergence/...` 组里，于是 dry run 报
> `already run: 10, to run: 0`，扫描会静默什么都不做。先清组归属：
>
> ```bash
> python tools/normalize_groups.py --set-names <SET> --convergence --dry-run
> python tools/normalize_groups.py --set-names <SET> --convergence
> ```
>
> 它只摘掉组成员资格，数据库节点与结果都不动。

结果（`2-convergence/convergence-report.md`，参考点 250 Ry）：

| ecutwfc | ν(U-X/BCC) | Δν | ε(U-X/BCC) | Δε | ν(O3U2-X2O3) | Δν | ε(O3U2-X2O3) | Δε |
|---|---|---|---|---|---|---|---|---|
| 100 | 0.6599 | — | 0.19348 | — | 0.3973 | — | 0.23707 | — |
| 110 | 0.1966 | -0.4633 | 0.06867 | -0.12481 | 0.1198 | -0.2775 | 0.03326 | -0.20381 |
| 120 | 0.0611 | -0.1355 | 0.01153 | -0.05714 | 0.1039 | -0.0160 | 0.04131 | +0.00805 |
| 150 | 0.0050 | -0.0560 | 0.00250 | -0.00904 | 0.0039 | -0.1000 | 0.00251 | -0.03880 |
| 200 | 0.0005 | -0.0046 | 0.00018 | -0.00231 | 0.0178 | +0.0139 | 0.00624 | +0.00373 |
| 250 | 0.0000 | -0.0005 | 0.00031 | +0.00013 | 0.0000 | -0.0178 | 0.00051 | -0.00573 |

* ν ≤ 0.2 % 判据 → **110 Ry**（但 BCC 那行 0.1966 是踩线，余量仅 1.7 %）；
  ε ≤ 0.01 判据 → **150 Ry**（最差 0.0025，余量 4 倍）。两者取严者仍是生产值
  **150/600 Ry，没有被推翻**；
* 每个截断点 28 个标准 SCF 全部 `convergence_achieved=True`；
* X₂O₃ 在 200 Ry 处 ν 由 0.0039 抬头到 0.0178（拟合质量正常，仍低于容差 11 倍），是该档数值
  抖动，也说明 200→250 之间 X₂O₃ 的 EOS 还没完全静止（相邻两点距离 ε = 0.00624）。

判据记录写在 `2-convergence/cutoffs-bcc-x2o3.json`（ν）与
`2-convergence/cutoffs-bcc-x2o3-epsilon.json`（ε）；旧结构对的报告另存为
`2-convergence/convergence-report-fcc-xo2.md`。

### 本项目采用的收敛判据：参考点 200 Ry，只看 ε ≤ 0.01

收敛报告里的 ν/ε 是**同一赝势在两个截断下自己跟自己比**（基组一致性），
**不是**对全电子参考的精度——后者在 `4-analyze/outputs/6P25-verification.md` §3，
用的是 `quantities_for_comparison.py` 的官方判据（ν ≤ 0.5 %、ε ≤ 0.05）。两者数量级差
约 40 倍，不要混用。

本项目把收敛判据定为：**每一档与 200 Ry 参考档比 ε，阈值 0.01**，结构取四组
（`U-X/BCC`、`O3U2-X2O3`、`U-X/FCC`、`O2U-XO2`）中最差者：

```bash
python 2-convergence/select_cutoffs.py --pseudos 6p25 --criterion epsilon --tolerance 0.01 \
    --reference-ecut 200 --systems U-X/BCC O3U2-X2O3 U-X/FCC O2U-XO2 \
    --output 2-convergence/cutoffs-epsilon.json
```

| ecutwfc | ε(U-X/BCC) | ε(U-X/FCC) | ε(O3U2-X2O3) | ε(O2U-XO2) | 判决 |
|---|---|---|---|---|---|
| 100 | 0.19335 | 0.15346 | 0.23124 | 0.12521 | 不收敛 |
| 110 | 0.06871 | 0.29695 | 0.03863 | 0.04141 | 不收敛 |
| 120 | 0.01158 | 0.07795 | 0.03569 | 0.02443 | 不收敛 |
| **150** | **0.00261** | **0.00811** | **0.00858** | **0.00964** | **收敛** |
| 200 | 0.00031 | 0.00072 | 0.00031 | 0.00045 | 参考点 |

**结论：150 / 600 Ry**，与 ν 判据（SSSP control protocol，参考 250 Ry）以及两组独立结构
的复核一致。注意余量很薄——最差 0.00964（`O2U-XO2`）距 0.01 只有 4 %，`O3U2-X2O3` 是
0.00858（14 %）；120 Ry 明确不收敛。若要让这条判据更从容，应把参考点抬到 300 Ry 再复算。

复现报告（短表只放当前这组结构，长表保留四个体系）：

```bash
python 2-convergence/make_convergence_report.py --pseudos 6p25 \
    --reference-ecut 200 --criterion epsilon \
    --systems U-X/BCC O3U2-X2O3 \
    --full-systems U-X/BCC O3U2-X2O3 U-X/FCC O2U-XO2 \
    --output 2-convergence/convergence-report.md
```

`--criterion epsilon` 让长表只输出 ε 判决列；`--reference-ecut 200` 让每一行都与 200 Ry 比
（因此 200 Ry 那行按定义为 0，而 250 Ry 那行不再为 0）。

记录文件：`2-convergence/cutoffs-epsilon.json`（本项目标准，四体系取最差，参考 200 Ry）、
`cutoffs-epsilon-ref200-{bcc-x2o3,fcc-xo2,all}.json`（分组明细）、
`cutoffs-epsilon-oldpair-ref200.json`（改用四体系前的旧记录备份）、
`cutoffs.json`（ν 判据，参考 250 Ry）、`cutoffs-bcc-x2o3*.json`（新结构对的 ν/ε 判据）。

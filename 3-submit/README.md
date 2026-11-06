# 3-submit — 提交 EOS 验证计算

`launch_calculations_qe.py` 与官方 `acwf-verification-scripts/2-submit/launch_calculations_qe.py`
结构相同：用 `FromGroupSubmissionController` 遍历某个 set 的 structures 组，
每个结构提交一个 `EquationOfStateWorkChain`（7 个体积，±6%，步长 2%），
默认 **dry run**，加 `--run` 才真正提交。

## 标准在哪里被钉死

`sub_process.base_relax` 显式注入（见 `common/util.py::build_sub_process`）：

```python
sub_process = {
    'base_relax': {
        'kpoints_distance': 0.06,                     # ACWF 标准
        'pw': {
            'pseudos':     {'U': <UpfData>, 'O': <UpfData>},   # 正在被测的那个赝势
            'parameters':  orm.Dict({...完整 pw 输入...}),      # 截断/收敛阈值/smearing
        },
    },
}
```

这样做的原因见主 README §1.1：本机的 ACWF `verification-PBE-v1` YAML 段落键名是
`aiida-quantumespresso` 4.x 的，在 5.x 下会被静默忽略。显式注入后，无论插件默认协议是什么，
每一次计算都严格遵循 ACWF/SSSP 标准，而这些值也会出现在每个 AiiDA 节点的 provenance 里。

> 注意：只有 `base_relax` 被覆盖。`base_init_relax` 是 QE ≥ 5.0 为几何优化准备的前置
> SCF，对 `relax_type = NONE`（EOS）没有意义；它会按**插件默认协议**解析赝势与参数
> （所以它的 provenance 里可能看到 `U-5spdf.upf`、`ecut 100/800`、`smearing cold` 等与本次
> 验证无关的输入），结果不被使用（只用于 `current_number_of_bands`，而 scf 模式下该量不参与
> 任何决策）。EOS 的能量/体积/应力全部来自 `base_relax`，已用 AiiDA 查询核实
> （见 `verify_setup.py` 第 4 节与本文档末尾的核查方法）。
> 打了 `1-preliminary/patch_acwf_qe_generator.py` 后这次多余的 SCF 会被完全去掉。

## 常用命令

```bash
# dry run（默认）
python 3-submit/launch_calculations_qe.py

# 正式提交（两个赝势，全部 10 个体系）
python 3-submit/launch_calculations_qe.py --run

# 官方推荐的长跑循环
while true ; do python 3-submit/launch_calculations_qe.py --run ; sleep 60 ; done

# 只跑单质 / 只跑一个赝势
python 3-submit/launch_calculations_qe.py --run --configurations X/SC X/BCC X/FCC X/Diamond
python 3-submit/launch_calculations_qe.py --run --pseudos sr

# 便宜的端到端预跑（独立 set，X/SC，3 个体积，粗 k 点）
python 3-submit/launch_calculations_qe.py --smoke-test --run

# fr 的 SOC 附加验证（单独 set；结果不与标量相对论参考对比）
python 3-submit/launch_calculations_qe.py --run --pseudos fr --spin-orbit

# 换用 SSSP 的 EOS 协议（conv_thr_per_atom = 1e-9）
python 3-submit/launch_calculations_qe.py --run --standard sssp-eos

# 指定收敛后的截断
python 3-submit/launch_calculations_qe.py --run --cutoffs 2-convergence/cutoffs.json
```

其他选项：`--max-concurrent N`（默认 24，同时运行的 EOS workchain 数）、
`--kpoints-distance`（**仅供调试**，偏离标准，脚本会提示）、
`--max-memory-gb G`（见下一节）。

## 内存不足（OOM）与 `--max-memory-gb`

`q_ysuan` 分区的默认内存是 **872 MB / core**：56 个 rank 的一个节点只拿到
**48828 MB（≈47.7 GiB）**，所以 `squeue` 里绝大多数作业显示 `MIN_MEMORY=48828M`。
大胞 + 高截断的体系会撞到这个限制，而不是撞到物理内存（节点实际有 ~165 GB 可用），
典型症状是

```
slurmstepd: error: Detected 35 oom-kill event(s) ...
KILLED BY SIGNAL: 9
```

以及 `verdi process show` 里 workchain 以 `exit 400`
（`ERROR_SCHEDULER_OUT_OF_MEMORY`）结束。已实测过：RC1 赝势的 `U-X/Diamond`
（8 原子，150/600 Ry，nbnd=154）在 48.8 GB 下必挂，在 100 GB 下正常。

AiiDA 的 SLURM 插件用 `max_memory_kb` 写出 `#SBATCH --mem=<MB>`，而 `--mem` 与
分区的 `--mem-per-cpu` 默认互斥，因此它会直接覆盖那个 872 MB/core 默认值。
`--max-memory-gb` 就是这个开关：

```bash
# 提高单节点内存上限并重跑某一个体系
python 3-submit/launch_calculations_qe.py --run --pseudos rc1 \
       --configurations X/Diamond --max-memory-gb 100
```

提交后用 `ssh yeesuan squeue -u $USER -o "%.9i %.22j %.2t %.10m %R"` 确认该作业的
`MIN_MEMORY` 已经是 `100G` 而不是 `48828M`。

重跑某个失败的体系前，先把它从 workflows 组里摘掉，否则 controller 认为
`(element, configuration)` 已完成而跳过：

```bash
python tools/normalize_groups.py --failed-only   # 只剔除终态失败的，保留正在跑的
```

（不带 `--failed-only` 的默认模式还会剔除**正在运行**的节点，campaign 进行中不要用。）


## 组标签与断点续跑

| 组 | 内容 |
|---|---|
| `acwf-verification/u14ve-<key>-verification-PBE-v1/structures/quantum_espresso` | 待算结构 |
| `acwf-verification/u14ve-<key>-verification-PBE-v1/workflows/quantum_espresso` | 已提交的 EOS workchain |

`--configurations` 只是在 structures 组下临时挂一个 `selected-<tag>` 子组作为 controller 的
parent group，workflows 组不变，所以分批提交、反复调用都不会重复计算
（controller 以 `(element, configuration)` 作为唯一键去重）。

`--smoke-test` 走独立的 set `u14ve-<key>-smoketest-verification-PBE-v1`，
不会污染正式结果。

## 观察运行状态

```bash
verdi process list -a -p 1                 # 正在跑 / 最近结束
verdi process status <PK>                  # 某个 EOS workchain 的调用树
verdi group show acwf-verification/u14ve-sr-verification-PBE-v1/workflows/quantum_espresso
```

核查某次 `pw.x` 真正用的赝势与参数（推荐的抽查方式）：

```python
from aiida import orm
node = orm.load_node(<PK of the PwCalculation>)
print({t.link_label: t.node for t in node.base.links.get_incoming().all()
       if t.link_label.startswith('pseudos')})
print(node.inputs.parameters.get_dict()['SYSTEM'])
print(node.inputs.kpoints.get_kpoints_mesh())
```

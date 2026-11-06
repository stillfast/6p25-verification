# 1-preliminary — 准备阶段

全部脚本都用普通 `python` 运行（脚本内部会 `load_profile`），必须在项目根目录下执行。

```bash
cd ../u14ve-verification        # 相邻的验证项目
conda activate aiida
```

## `install_pseudos.py`

上传两个候选铀赝势与配套的 NC 氧赝势，为每个铀赝势建一个
`CutoffsPseudoPotentialFamily`（含 `U` + `O`），并建立
`acwf-verification/<set>/pseudo/quantum_espresso` 文档组。脚本是幂等的，可以反复运行。

同时会检查 ACWF 输入生成器默认解析的 `pseudo_family` 是否存在——它必须先存在，
我们自己的赝势覆盖才会生效；缺失时可以用 `--fix-generator-family` 自动创建。

## `create_starting_subgroups.py`

把已发表的 `uranium-verification-PBE-v1` 十个结构（4 个单质 + 6 个氧化物）**按节点引用**
放进每个 set 的 structures 子组。两个赝势用的是同一批 StructureData，
这是后面能直接对比的前提。

```bash
python 1-preliminary/create_starting_subgroups.py                  # 全部 10 个 + fr 的 SOC 组
python 1-preliminary/create_starting_subgroups.py --no-soc         # 不要 SOC 组
python 1-preliminary/create_starting_subgroups.py --configurations X/BCC XO2
```

## `verify_setup.py` ★

**这是最重要的一个脚本，正式提交前必跑。** 它不信任任何"协议应该生效"的假设，而是像
EOS workchain 那样重建子流程 builder（ACWF input generator + `sub_process` merge），
逐项核对：

1. profile / code / 插件；
2. pseudo family 的元素、`z_valence`、截断表；
3. structure 组是否就绪；
4. 有效 `pw.x` 输入：赝势文件名、`ecutwfc`/`ecutrho`、`kpoints_distance`、`conv_thr`、
   `etot_conv_thr`、`forc_conv_thr`、smearing/degauss、SOC 标志；
5. k 点网格（会打印实际 MP 网格，用于估算计算量）；
6. **提交级输入校验**：对每个结构 × 每个赝势，按 AiiDA 提交时的做法
   （`spec().inputs.serialize` + `validate`）校验 EOS 输入与子流程输入——
   这一步能抓出"多余/类型不对的输入端口"这类只在运行时才暴露的问题；
7. ACWF `verification-PBE-v1` 协议段落的诊断（见主 README §1.1）。

任何一项失败都会以非零退出码结束。

## `patch_acwf_qe_generator.py`（可选）

只做两件事，都是对已安装包文件的修改（带 `*.u14ve-backup` 备份，可 `--restore` 还原）：

1. 把 ACWF `protocol.yml` 里 `verification-PBE-v1` 的键名从 4.x 的
   `base`/`base_final_scf` 改成 5.x 的 `base_relax`/`base_init_relax`，
   让记录下来的协议真正生效、自洽；
2. 在生成器里为 `relax_type = NONE`（即 EOS）去掉无用的 `base_init_relax`
   前置 SCF，使每个体积少跑一次完整 SCF（计算量减半）。

**本工作流不依赖这个补丁**：标准通过 `sub_process` 强制，`verify_setup.py` 已确认无误。
补丁只是让 provenance 更干净、更快。

```bash
python 1-preliminary/patch_acwf_qe_generator.py --check
python 1-preliminary/patch_acwf_qe_generator.py --apply
python 1-preliminary/patch_acwf_qe_generator.py --restore
```

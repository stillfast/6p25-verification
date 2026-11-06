# 5-export — 导出 AiiDA 归档

每个 set 导出一个自包含的 `.aiida` 归档（结构组 + workflows 组 + 它们依赖的所有
calculation、赝势、code/computer 描述），可在别的机器上 `verdi archive import` 后复现分析。

```bash
bash 5-export/export_results.sh              # 两个赝势
bash 5-export/export_results.sh sr           # 只导出标量相对论那个
bash 5-export/export_results.sh sr fr --spin-orbit   # 连带 SOC 组
```

输出：`outputs/export-<set>.aiida`（项目根目录的 `outputs/`）。

同时建议把 `4-analyze/outputs/` 下的
`results-*.json`、`warnings-*.txt`、`metrics-*.json`、`metrics-*.md`、`plots/`
一起归档保存——这些是最终汇报用的产物。

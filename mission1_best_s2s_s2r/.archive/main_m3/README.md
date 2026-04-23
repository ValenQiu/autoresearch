# Archive: M3 第一版计划与弃用文档

本目录存放 **M3 Sim2Real 第一次尝试** 相关的计划、对齐矩阵、风险清单与 runbook。**除非用户明确要求启用备份，否则本目录内容不参与当前 `sim2real_redo` 分支的开发决策**。

## 背景

- **锚点 commit（UHC）**：`02e7e79e4b8d9a315dbb6c888af8774da54f1d0a`（`feat(bfm-zero): ...`，2026-04-16）
- **第一次尝试**：UHC `main` 分支 = `02e7e79 + 5 commit`，已打 tag `archive/main-m3-attempt1` → `e1c664a`；接近完成但被顽固 bug 拖死
- **第二次尝试**：UHC `sim2real_debug` 分支 = `02e7e79 + 6 commit`，已打 tag `archive/sim2real-debug-m3-attempt2` → `0a661b6`；同样失败
- **当前重置基线**：UHC `sim2real_redo` 分支 = `02e7e79 + b791b1c`（仅保留 wandb 预下载工具）

## 归档内容

| 文件 | 作用 | 当前状态 |
|------|------|----------|
| `m3_original_deprecated.md` | 原 `m3_sim2real.md` 的「历史归档 (Deprecated)」段，描述 M3.0~M3.5 的原始 UnitreeBackend + loopback 细节设计 | 冻结，仅参考 |
| `rebuild_m3_acceptance_matrix.md` | 为 sim2real_debug 重建路径准备的 ASAP 语义对齐矩阵 | 随 attempt2 一起弃用 |
| `review_uhc_vs_mtc_loopback_alignment.md` | attempt2 期间对 motion_tracking_controller 的对照审查 | 结论过时 |
| `runbook_loopback_uhc_mujoco.md` | attempt2 期间的 loopback 操作 runbook | 针对已弃用代码 |
| `s3_s4_loopback_risks_and_checklist.md` | attempt2 的风险与 checklist | 与 sim2real_debug 绑定 |

## 启用备份的条件

仅在以下情况由用户明确要求时，才重新引用本目录内容：

1. **差分审查需要**：对照 M3 两次尝试与 `sim2real_redo` 实际实现，评估回归风险
2. **挽救部分设计**：某条对齐矩阵条目或某个 runbook 步骤被判定「仍有参考价值」，可单条/单段回捡
3. **失败复盘**：总结两次 attempts 的失败路径，写成研究文档或 skill

未获用户明示前，**agent 禁止**在 `sim2real_redo` 的开发讨论、规划、commit message 里引用本目录文件。

## 相关（未归档，保留日常引用）

- `../m3_sim2real.md` — 新的 M3 顶层方案（锚点 `02e7e79`，分支 `sim2real_redo`）
- `../plan_uhc_unitree_sdk_mujoco_mock.md` — mock 桥方案设计（会在 sim2real_redo 中重新评估）
- `../sop_sim2sim_to_sim2real.md` — 跨版本通用 SOP
- `../research/robojudo_teacher_distilled.md` — teacher 调研（与 attempt 无强绑定）
- `../research/m3_r5_main_vs_sim2real_debug_diff_review.md` — 两次 attempts 的差分审查报告
- UHC 归档 tag：`archive/main-m3-attempt1`、`archive/sim2real-debug-m3-attempt2`

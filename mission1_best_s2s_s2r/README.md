# Mission 1: Best Sim2Sim & Sim2Real Controller

构建 SOTA 级别的通用 sim2sim & sim2real 人形机器人运控部署工具。

## Milestones

| ID | 名称 | 范围 | 状态 |
|----|------|------|------|
| M0 | 项目基建与环境配置 | 基础设施 | **完成** |
| M1 | 核心框架 + ASAP Locomotion 基线 | sim2sim | **完成** |
| M1.5 | ASAP Mimic 切换 + 操作流程打磨 | sim2sim loco↔mimic | **完成** |
| M2 | BeyondMimic 适配 + 策略切换 | sim2sim 多策略 | **完成** |
| M3 | Sim2Real + 安全 + 多输入 | 真机 | **项目级重置 (2026-04-23)**：attempt1/2 归档；从 UHC `02e7e79` 起 `sim2real_redo`；P0/P1 已完成，P2 对齐矩阵待开始 |
| M4 | 多策略在线切换 + 通用底座（BFM-Zero） | sim2sim 策略生态 | **完成（带条件验收，2026-04-17）**：见 `task_best_s2s_s2r.json` 中 `acceptance_conditions`；**M4.3b** 延后 |
| M5 | 通用追踪器 + 参考动作流式输入（SONIC/OpenTrack/BFM-Zero） | 开放式策略 | 待开始 |
| M6 | 遥操作（Pico VR / MoCap） | 实时人类输入 | 待开始 |
| M7 | 高层自主性（Text2Motion / VLM / VLA） | AI 驱动 | 待开始 |

## **文件说明**

| 文件 | 内容 |
|------|------|
| `AGENTS.md`（仓库根目录） | Agent 可见 skills 列表；入口 skill = `autoresearch-house-rules` + `karpathy-coding-discipline`；新策略接入 UHC 前先读 `uhc-policy-adaptation` |
| `task_best_s2s_s2r.md` | 任务全文 v2.0（目标/架构/需求/milestone/配置精简分析） |
| `task_best_s2s_s2r.json` | 结构化配置（机器可读），含 M3 重置决定与 archived_branches |
| `m0_project_infra.md` | M0 执行计划（环境/基建） |
| `m1_asap_loco_baseline.md` | M1 执行计划（核心框架 + ASAP loco）✅ |
| `m1_5_asap_mimic_switch.md` | M1.5 执行计划（ASAP Mimic + 切换流程打磨）✅ |
| `m1_5_verification_plan.md` | M1.5 与 ASAP 对齐验证记录（CR7 等问题） |
| `superpowers_workflow.md` | Superpowers skills 与仓库规范（DEVELOPMENT_RULES / selftest）融合说明 |
| `m2_beyondmimic_switch.md` | M2 执行计划（BeyondMimic + 切换）✅ |
| `m4_multi_policy_switch.md` | M4.1 多策略透明中转（PolicyRunner 机制说明）✅ |
| `m3_sim2real.md` | M3 执行计划（**2026-04-23 重置后**的新方案，锚点 UHC `02e7e79`，分支 `sim2real_redo`）🚧 |
| `.archive/main_m3/` | M3 两次 attempt 的归档（`m3_original_deprecated.md` / `rebuild_m3_acceptance_matrix.md` / `review_uhc_vs_mtc_loopback_alignment.md` / `runbook_loopback_uhc_mujoco.md` / `s3_s4_loopback_risks_and_checklist.md`）；未用户明示不参与当前开发 |
| `plan_uhc_unitree_sdk_mujoco_mock.md` | mock 桥方案设计（将在 sim2real_redo P4 重新评估） |
| `sop_sim2sim_to_sim2real.md` | 跨版本通用 SOP |
| `research/asap_sim2real_analysis.md` | ASAP 架构调研报告 |
| `research/motion_tracking_controller_postmortem.md` | dummy_task 复盘报告 |
| `research/omnixrtreme_uhc_adaptation.md` | OmniXtreme→UHC 适配复盘 |
| `research/m4_2_bfm_zero_vs_host.md` | M4.2 BFM-Zero vs HoST 选型报告 |
| `research/m3_r5_main_vs_sim2real_debug_diff_review.md` | attempt1/attempt2 差分审查（Gate D 复盘参考） |
| `research/robojudo_teacher_distilled.md` | teacher 调研（M3 重做可参考） |
| `.cursor/skills/uhc-interpolation-debugging/SKILL.md` | base↔task 插值异常标准排错流程 |

## 快速导航

- **项目是什么？** → `task_best_s2s_s2r.md` §1-2
- **现在该做什么？** → **M3-P2**（对齐矩阵重冻，在 UHC `sim2real_redo` 上；见 `m3_sim2real.md` §0.2）；并行可推进 **M5**（通用追踪器 / MotionProvider）。
- **M3 历史为什么重置？** → `m3_sim2real.md` §0.2 + `.archive/main_m3/README.md` + UHC tag `archive/main-m3-attempt1` / `archive/sim2real-debug-m3-attempt2`
- **之前为什么失败？** → `research/motion_tracking_controller_postmortem.md`
- **ASAP 代码怎么工作？** → `research/asap_sim2real_analysis.md`
- **配置怎么简化？** → `task_best_s2s_s2r.md` §8

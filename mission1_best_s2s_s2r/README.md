# Mission 1: Best Sim2Sim & Sim2Real Controller

构建 SOTA 级别的通用 sim2sim & sim2real 人形机器人运控部署工具。

## Milestones

| ID | 名称 | 范围 | 状态 |
|----|------|------|------|
| M0 | 项目基建与环境配置 | 基础设施 | **完成** |
| M1 | 核心框架 + ASAP Locomotion 基线 | sim2sim | **完成** |
| M1.5 | ASAP Mimic 切换 + 操作流程打磨 | sim2sim loco↔mimic | **完成** |
| M2 | BeyondMimic 适配 + 策略切换 | sim2sim 多策略 | **完成** |
| M3 | Sim2Real + 安全 + 多输入 | 真机 | 待开始（等真机） |
| M4 | 多策略在线切换 + 通用底座（BFM-Zero） | sim2sim 策略生态 | **进行中**：**M4.1**、**M4.2**、**M4.4** 已完成；**M4.3** 待开始 |
| M5 | 通用追踪器 + 参考动作流式输入（SONIC/OpenTrack/BFM-Zero） | 开放式策略 | 待开始 |
| M6 | 遥操作（Pico VR / MoCap） | 实时人类输入 | 待开始 |
| M7 | 高层自主性（Text2Motion / VLM / VLA） | AI 驱动 | 待开始 |

## **文件说明**

| 文件 | 内容 |
|------|------|
| `AGENTS.md`（仓库根目录） | Agent 可见 skills 列表；**新策略接入 UHC 前先读 `uhc-policy-adaptation`** |
| `task_best_s2s_s2r.md` | 任务全文 v2.0（目标/架构/需求/milestone/配置精简分析） |
| `task_best_s2s_s2r.json` | 结构化配置（机器可读） |
| `m0_project_infra.md` | M0 执行计划（环境/基建） |
| `m1_asap_loco_baseline.md` | M1 执行计划（核心框架 + ASAP loco）✅ |
| `m1_5_asap_mimic_switch.md` | M1.5 执行计划（ASAP Mimic + 切换流程打磨）✅ |
| `m1_5_verification_plan.md` | M1.5 与 ASAP 对齐验证记录（CR7 等问题） |
| `superpowers_workflow.md` | Superpowers skills 与仓库规范（DEVELOPMENT_RULES / selftest）融合说明 |
| `m2_beyondmimic_switch.md` | M2 执行计划（BeyondMimic + 切换）✅ |
| `m4_multi_policy_switch.md` | M4.1 多策略透明中转（PolicyRunner 机制说明）✅ |
| `m3_sim2real.md` | M3 执行计划（Sim2Real + 安全 + 多输入）🚧 |
| `research/asap_sim2real_analysis.md` | ASAP 架构调研报告 |
| `research/motion_tracking_controller_postmortem.md` | dummy_task 复盘报告 |
| `research/omnixrtreme_uhc_adaptation.md` | OmniXtreme→UHC 适配复盘（配置对齐、`clip_action` 根因、skill 索引） |
| `research/m4_2_bfm_zero_vs_host.md` | M4.2 BFM-Zero vs HoST 选型报告 + 实现交付物清单 + 插值异常排障补充 |
| `.cursor/skills/uhc-interpolation-debugging/SKILL.md` | base↔task 插值异常（腰部跳变/前倾）标准排错流程 |

## 快速导航

- **项目是什么？** → `task_best_s2s_s2r.md` §1-2
- **现在该做什么？** → **M4.3** 通用底座 GUI 验证 + RECOVERING 状态机；可选补 M4.1「5 次切换」专项验收与 selftest；**M3** 等真机；新策略接入先读 `.cursor/skills/uhc-policy-adaptation/SKILL.md`
- **之前为什么失败？** → `research/motion_tracking_controller_postmortem.md`
- **ASAP 代码怎么工作？** → `research/asap_sim2real_analysis.md`
- **配置怎么简化？** → `task_best_s2s_s2r.md` §8

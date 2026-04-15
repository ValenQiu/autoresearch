# Mission 1: Best Sim2Sim & Sim2Real Controller

构建 SOTA 级别的通用 sim2sim & sim2real 人形机器人运控部署工具。

## Milestones

| ID | 名称 | 范围 | 状态 |
|----|------|------|------|
| M0 | 项目基建与环境配置 | 基础设施 | **完成** |
| M1 | 核心框架 + ASAP Locomotion 基线 | sim2sim | **完成** |
| M1.5 | ASAP Mimic 切换 + 操作流程打磨 | sim2sim loco↔mimic | 待开始 |
| M2 | BeyondMimic 适配 + 策略切换 | sim2sim 多策略 | 待开始 |
| M3 | Sim2Real + 安全 + 多输入 | 真机 | 待开始 |
| M4 | 多策略 + HoST + 生产化 | 策略生态 | 待开始 |

## **文件说明**

| 文件 | 内容 |
|------|------|
| `task_best_s2s_s2r.md` | 任务全文 v2.0（目标/架构/需求/milestone/配置精简分析） |
| `task_best_s2s_s2r.json` | 结构化配置（机器可读） |
| `m0_project_infra.md` | M0 执行计划（环境/基建） |
| `m1_asap_loco_baseline.md` | M1 执行计划（核心框架 + ASAP loco）✅ |
| `m1_5_asap_mimic_switch.md` | M1.5 执行计划（ASAP Mimic + 切换流程打磨） |
| `m2_beyondmimic_switch.md` | M2 执行计划（BeyondMimic + 切换） |
| `research/asap_sim2real_analysis.md` | ASAP 架构调研报告 |
| `research/motion_tracking_controller_postmortem.md` | dummy_task 复盘报告 |

## 快速导航

- **项目是什么？** → `task_best_s2s_s2r.md` §1-2
- **现在该做什么？** → `m0_project_infra.md`
- **之前为什么失败？** → `research/motion_tracking_controller_postmortem.md`
- **ASAP 代码怎么工作？** → `research/asap_sim2real_analysis.md`
- **配置怎么简化？** → `task_best_s2s_s2r.md` §8

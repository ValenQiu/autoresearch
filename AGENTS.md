# Agent 指引（Autoresearch 体系）

本文件供 **Cursor / Codex / 其他 Agent** 与人类协作者阅读：列出与本仓库相关的**团队可见 skills** 与强制顺序。

## 入口 skill（任何任务先读）

| Skill | 作用 |
|-------|------|
| **autoresearch-house-rules** | [`.cursor/skills/autoresearch-house-rules/SKILL.md`](.cursor/skills/autoresearch-house-rules/SKILL.md) — 项目强制规范 + skill 导航总表 |
| **karpathy-coding-discipline** | [`.cursor/skills/karpathy-coding-discipline/SKILL.md`](.cursor/skills/karpathy-coding-discipline/SKILL.md) — 通用编码纪律（Think / Simplicity / Surgical / Goal-Driven），[`CLAUDE.md`](CLAUDE.md) 顶部的 skill 化版本 |

两者一起构成：**通用编码纪律 + 本仓库强制规范 + 跨 skill 导航**。其余 skill 由这两份按触发场景指引加载。

## 新策略 / 新 ONNX 接入 UHC 时（强制）

**在修改 `universal_humanoid_controller` 的 Policy 类、策略 YAML、或仿真/安全相关代码之前，必须先阅读 skill：**

| Skill | 路径 |
|-------|------|
| **uhc-policy-adaptation** | [`.cursor/skills/uhc-policy-adaptation/SKILL.md`](.cursor/skills/uhc-policy-adaptation/SKILL.md) |

内容涵盖：物理节拍与 XML 对齐、电机包络与 per-substep 摩擦、`SafetyGuard.clip_action` 与 `skip_position_clip`、FM `initial_noise`、与参考 `deploy_*.py` 的逐项对照。遗漏易导致「参考稳定、UHC 倒地」。

详细清单与仓库规范另见根目录 [`DEVELOPMENT_RULES.md`](DEVELOPMENT_RULES.md) §「适配新网络时的对齐清单」。

## 自测与真实路径对齐（强制）

| Skill | 路径 |
|-------|------|
| **selftest-reality-alignment** | [`.cursor/skills/selftest-reality-alignment/SKILL.md`](.cursor/skills/selftest-reality-alignment/SKILL.md) |

编写或审查 `selftest.py`、声称集成测试通过时，须满足与 `PolicyRunner` / profile 一致的路径与时序。见 [`DEVELOPMENT_RULES.md`](DEVELOPMENT_RULES.md) §1。

## Superpowers 流程型 skills

流程纪律（brainstorm、TDD、完成前验证等）见 submodule **`third_party/superpowers/`** 与 [`.cursor/skills/superpowers-*/`](.cursor/skills/)，融合说明见 [`mission1_best_s2s_s2r/superpowers_workflow.md`](mission1_best_s2s_s2r/superpowers_workflow.md)。

## 仅克隆 UHC 仓库时

若工作区只有 `universal_humanoid_controller` 而无本 autoresearch 仓库，请将上述 `SKILL.md` 复制到本机 `~/.cursor/skills/<name>/SKILL.md`，或从本仓库拉取同路径文件，规则仍适用。

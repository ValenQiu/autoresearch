---
name: autoresearch-house-rules
description: >-
  Navigation + mandatory-compliance skill for the autoresearch monorepo. Use at
  the start of any task touching autoresearch or universal_humanoid_controller,
  whenever planning a new milestone, before writing selftest, before adapting a
  new ONNX policy, or before updating skills/docs. Collapses CLAUDE.md /
  AGENTS.md / DEVELOPMENT_RULES.md into a single entry point with pointers to
  the specialized skills that actually enforce each area.
---

# Autoresearch House Rules

## 何时启用

- 在 autoresearch 仓内开始任何 coding / doc / planning 工作
- 在 `universal_humanoid_controller` 仓内开发，但任务跨越项目规范（新策略、selftest、sim2real 通信）
- 规划新 mission / 新 milestone / 新 skill
- 审查他人 commit 是否符合项目强制规范

## 源文档

本 skill 与 `karpathy-coding-discipline` **即是 canonical 源**（入库 + 跨仓镜像），不依赖 launcher 生成的 `CLAUDE.md`。参考关系：

| 文档 | 入库状态 | 作用 |
|------|----------|------|
| `karpathy-coding-discipline` (skill) | ✅ tracked | 通用编码纪律（四条 Karpathy 准则的可执行清单） |
| `autoresearch-house-rules` (本 skill) | ✅ tracked | 本仓库强制规范 + skill 导航 |
| [`../../AGENTS.md`](../../AGENTS.md) | ✅ tracked | 团队 skills 总表（入口指向两个 skill） |
| [`../../DEVELOPMENT_RULES.md`](../../DEVELOPMENT_RULES.md) | ✅ tracked | 逐条项目强制规范（selftest 先行等） |
| `../../CLAUDE.md` | ❌ 在 `.gitignore`（launcher session 生成） | 本地运行时便利视图；**不是** canonical；若与本 skill 冲突以 skill 为准 |

GitHub 入口（从 UHC 镜像加载、相对路径不通时使用）：<https://github.com/ValenQiu/autoresearch>

## 项目强制规范 → 对应 skill

按「触发场景 → 先读哪个 skill → 再动手」展开：

| 触发 | 先读 skill | 文档依据 |
|------|-----------|----------|
| 通用编码纪律（每次 coding 任务） | `karpathy-coding-discipline` | `CLAUDE.md` 顶部 |
| 写 / 改 `scripts/selftest.py` 或 集成测试 | `selftest-reality-alignment` | `DEVELOPMENT_RULES.md` §1 |
| 新 ONNX 策略接入 UHC / deploy_* 对齐 / sim2sim 不稳定 | `uhc-policy-adaptation` | `AGENTS.md` §UHC；`DEVELOPMENT_RULES.md` §「适配新网络时的对齐清单」 |
| whole-body tracker（BM/ASAP/OmniXtreme/ProtoMotions/...）接入 / loopback 摔倒 / "RoboJuDo 能做为什么我们不能" | `robojudo-policy-adaptation` | `mission1_best_s2s_s2r/research/robojudo_teacher_distilled.md` |
| base↔task 插值期腰部跳变 / 前倾 | `uhc-interpolation-debugging` | `mission1_best_s2s_s2r/README.md` |
| sim2real LowCmd/LowState DDS、loopback mock、`lo→enp2s0` 切换 | `unitree-g1-sdk-dds-mock` | UHC `sim2real_redo` 分支开发约定 |
| G1 真机启动 / 安全 / SDK DDS 集成 / 低层控制 | `unitree-g1-documentation-distilled` | UHC `sim2real_redo` 分支开发约定 |
| 探索未知需求 / 2 种以上方案要选 | `superpowers-brainstorming` | `superpowers_workflow.md` |
| 实现任何功能 / bugfix | `superpowers-test-driven-development` | `superpowers_workflow.md`；`DEVELOPMENT_RULES.md` selftest-first |
| 遇 bug / 意外行为 | `superpowers-systematic-debugging` | `superpowers_workflow.md` |
| 声称"完成 / 修好 / pass"前 | `superpowers-verification-before-completion` | `CLAUDE.md` §4 Goal-Driven |
| 写 / 改 skill 本身 | `superpowers-writing-skills` | `AGENTS.md` |

## UHC 仓库快速上下文入口（节省 token）

**不要在对话开头全量读大文件。按下表选最小需要读取的内容：**

| 你要做什么 | 只读这个 |
|-----------|---------|
| 了解当前开发状态 / 未解问题 | `DEVELOPMENT_STATUS.md`（UHC 根目录，< 60 行） |
| Omni 切换失稳 debug | `scripts/debug_omni_handover.py`（独立，< 15s 运行） |
| PolicyRunner task 切换流程 | `uhc/core/policy_runner.py:407-480` |
| Omni policy 首帧对齐 / reset | `uhc/policies/omnixrtreme.py:363-515` |
| Omni 配置参数 | `config/policies/omnixrtreme.yaml`（88 行） |
| 全量验收（确认无回归） | `python scripts/selftest.py`（完整 11 项，3-5 分钟） |
| 排障历史 / 背景 | `docs/sim2real_loopback_debug_playbook.md`（仅在确实需要时） |

**对话开始时禁止做：** 全量读 `selftest.py`（1300+ 行）、`policy_runner.py`（825 行）、`omnixrtreme.py`（1100+ 行）、或 playbook；它们拖慢推理且 99% 的信息在当前任务中无用。

### 最小 token 的会话开场公式

```
背景：UHC sim2real_redo 分支。
本次目标：[一句话]
check.sh 输出：[粘贴 < 30 行输出]
请：[一个具体操作]
```

**每次会话只做一件事**（修参数 / 跑测试 / 写文档 = 三件事分三次会话）。多目标 = 长摘要 = 下次开销翻倍。

## 硬性红线（违反即停）

1. **自测先行**：没有 headless selftest、没有明确 PASS/FAIL 的 feature，不算完成（`DEVELOPMENT_RULES.md` §1）
2. **自测–真实路径对齐**：selftest 必须走与 `PolicyRunner` / profile 一致的代码路径（`selftest-reality-alignment`）
3. **急停仅按键**：`PolicyRunner` 禁止新增任何自动 `E_STOP` 触发（项目级约束，见 `uhc-policy-adaptation`）
4. **canonical skill 在 autoresearch**：UHC 的 `.cursor/skills/` 是镜像，修改先提 autoresearch 再回同步（UHC `AGENTS.md`）
5. **anchor + 排除范围**：所有"M3 后续"讨论以 UHC `02e7e79` 为锚点；`main` 与 `sim2real_debug` 仅作 tag 归档，除非用户显式启用（见 mission1 `task_best_s2s_s2r.json.base_commit_for_rebuild`）

## 用法流程

1. 任何新任务 → 先读本 skill → 顺着"触发 → 先读 skill"表判断还需加载哪些
2. 发现本表与源文档不一致 → 以源文档为准，**同时** 立即提醒用户修复本 skill
3. 任务结束前 → 对照"硬性红线"过一遍

## 与 `karpathy-coding-discipline` 的分工

- `karpathy-coding-discipline`：**通用**开发纪律（跨项目通用）
- `autoresearch-house-rules`（本 skill）：**本仓库特有**的强制规范 + skill 导航
- 两者互补：通用准则指导"如何写代码"，本 skill 指导"本仓的硬约束与 skill 组合"

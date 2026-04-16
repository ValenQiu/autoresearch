---
name: uhc-interpolation-debugging
description: Use when debugging base↔task transition anomalies in universal_humanoid_controller, especially waist bend, forward lean, or abnormal switch duration during interpolation.
---

# UHC 插值切换排障

## Overview

`PolicyRunner` 的切换异常常见于“插值起点”和“策略命令方差”不匹配。核心原则：**插值必须从切换当帧的真实关节姿态出发，而不是历史缓存或策略命令值。**

## When to Use

- `BASE_ACTIVE -> TASK_ACTIVE` 出现腰部突跳、前倾、先弯后回正
- `TASK_ACTIVE -> BASE_ACTIVE` 返回时上身姿态不自然
- 某个策略切换慢 1s 以上，怀疑插值时长配置不一致
- BFM-Zero / BeyondMimic / OmniXtreme 混合 profile 下出现切换体感不一致

## When NOT to Use

- 策略在稳定运行期（非切换窗口）倒地
- 纯键位分发问题（按键无响应）
- 与插值无关的观测拼接错误

## 标准排错流程

### 1) 先定位是“路径错误”还是“时长错误”

1. 记录切换日志：进入/退出策略时打印 `duration`
2. 对比各策略配置：`interpolation.loco_to_task_duration_s` 与 `task_to_loco_duration_s`
3. 若慢在固定时长：先统一 YAML 时长，再看姿态

### 2) 检查插值起点来源（最高优先级）

在 `uhc/core/policy_runner.py` 检查：

- `_begin_enter_task()`：起点应为 `state["joint_pos"][num_lower:]`
- `_begin_exit_task()`：起点应为 `state["joint_pos"][num_lower:]`

如果使用了 `_last_base_q_target` / `_last_task_q_target` 作为上肢插值起点，通常会导致可见姿态偏转（尤其是 BFM-Zero）。

### 3) 用三路对比法快速定性

固定同一 profile、同一 conda 环境，比较以下三种起点：

- `zero`：通常“位置跳变 + 力矩跳变”
- `command`：力矩连续，但容易“持续前倾/侧倾”
- `actual`：姿态最物理一致，通常是最终方案

输出最少三项指标（腰 yaw/roll/pitch）：

- `cmd`（策略命令）
- `actual`（真实关节）
- `gap = cmd - actual`

若 `command` 与 `actual` 偏差很大（例如 20-90deg），禁止用命令值起插值。

### 4) 双向回归（必须）

修复后必须回归两个方向：

- `BASE_ACTIVE -> TASK_ACTIVE`
- `TASK_ACTIVE -> BASE_ACTIVE`

只修 enter 不修 exit，常会在返回 base 时复发。

## 时长对齐建议

若目标是统一体感，优先将主流 task 策略的 enter/exit 对齐。例如：

- ASAP Mimic: `1.5s / 1.5s`
- BeyondMimic: 建议对齐到 `1.5s / 1.5s`
- OmniXtreme: 建议对齐到 `1.5s / 1.5s`

## 常见误区

- “力矩连续优先于姿态正确”：错误。命令值起插值可能力矩连续，但会把机器人引向错误姿态
- “只修一侧方向”：错误。enter 和 exit 必须成对验证
- “只看 headless”：错误。切换姿态必须在 GUI 下肉眼复核

## Skill 使用示例

以下示例用于快速复现并定位 “base->task 腰部前倾/跳变”：

1. 启动复现 profile（`robo_deploy` 环境）：

```bash
conda run -n robo_deploy python scripts/run.py --profile config/profiles/sim2sim_bfm_zero_all.yaml
```

2. 触发切换路径并观察日志：

- 先 `]` 进入 `BASE_ACTIVE`
- 用 `;` / `'` 选中目标 task（ASAP/BeyondMimic/OmniXtreme）
- 按 `[` 执行 `BASE_ACTIVE -> TASK_ACTIVE`
- 记录日志中的插值时长（`(1.5s)`）与视觉表现（是否前倾）

3. 按本 skill 做代码核查：

- `uhc/core/policy_runner.py::_begin_enter_task`
- `uhc/core/policy_runner.py::_begin_exit_task`
- 两处起点都应来自 `state["joint_pos"][num_lower:]`

4. 最小数值自测（command vs actual 差异）：

```bash
conda run -n robo_deploy python - <<'PYEOF'
import numpy as np
print("示意：请在你的诊断脚本中输出 waist yaw/roll/pitch 的 cmd/actual/gap")
print("判据：若 |cmd-actual| 持续很大（如 20-90deg），禁止用 command 作为插值起点")
PYEOF
```

5. 回归验收（必须双向）：

- `BASE_ACTIVE -> TASK_ACTIVE`：无腰部前倾/突跳
- `TASK_ACTIVE -> BASE_ACTIVE`：无回程姿态异常

## 快速检查清单

- [ ] enter/exit 起点都来自 `state["joint_pos"]`
- [ ] 无 `_last_*_q_target` 作为上肢插值起点
- [ ] BeyondMimic/OmniXtreme 插值时长已与 ASAP 对齐（如需）
- [ ] base->task 与 task->base 均已完成回归

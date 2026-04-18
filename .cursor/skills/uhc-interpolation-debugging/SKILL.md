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
- “恢复失败自动 E-STOP 更安全”：在本项目约束下错误。急停仅允许手动 `o`，自动流程应告警并回退
- “自动 recovery 直接沿用当前 z”：错误。会引入不确定性，必须切到固定 recovery z（可用中性 reward `move-ego-0-0`，或按本技能提取并固化的 `tracking_tpose_step0`）

## 将 `n-p-t` 姿态固化为可复现 recovery 目标（推荐）

当人工操作中出现“按 `n-p-t` 后姿态很好（接近 T-pose）”时，不要依赖人工按键复现，按以下步骤固化：

1. **确认根因是 `t` 覆盖**  
   `n/p` 切的是 goal z；最终姿态由 `t -> advance_tracking_z()` 覆盖后的 tracking latent 决定。

2. **离线复刻 `advance_tracking_z()`（step=0）**  
   使用当前 YAML 的 `z_tracking_gamma` / `z_tracking_window`，对 `zs_walking.pkl` 计算：
   - 折扣加权窗口平均
   - 按 `||seq[0]||` 做范数重标定  
   产出 `tracking_tpose_step0`（shape `(1, 256)`）。

3. **写入自定义 goal pkl（不要覆盖原文件）**  
   复制 `goal_reaching.pkl` 为 `goal_reaching_with_tracking_tpose.pkl`，新增 key：`tracking_tpose_step0`。

4. **让 recovery 走 goal 固定 key**  
   在 `bfm_zero.yaml` 中：
   - `z_sources.goal: ../goal_inference/goal_reaching_with_tracking_tpose.pkl`
   - `recovery.z_source: goal`
   - `recovery.z_name: tracking_tpose_step0`

5. **回归验证**  
   要求 `TASK_ACTIVE -> RECOVERING -> BASE_ACTIVE` 多次复现一致，无需人工 `n/p/t`。

## SOP（可直接复用）

### 目标

将“人工 `n-p-t` 才能触发的理想恢复姿态”固化为**配置驱动、可重复、可回归测试**的 recovery 目标。

### 触发条件

- 手动 `n-p-t` 后姿态明显优于现有 recovery 目标
- 同一环境下可重复复现（至少 3 次）
- 该姿态不依赖临时人工输入保持

### 执行步骤

1. **基线确认**  
   记录当前 `bfm_zero.yaml` 中 `z_tracking_gamma` / `z_tracking_window`，并确认 `recovery` 当前目标。

2. **提取 latent**  
   用 `advance_tracking_z()` 同公式在 `step=0` 计算目标 latent，命名 `tracking_tpose_step0`。

3. **固化资产**  
   新建 `goal_reaching_with_tracking_tpose.pkl`，保留原 goal，新增 `tracking_tpose_step0`（不覆盖原文件）。

4. **切换配置**  
   - `z_sources.goal` 指向新 pkl  
   - `recovery.z_source: goal`  
   - `recovery.z_name: tracking_tpose_step0`

5. **自动化验证**  
   运行自测（如 `selftest.py`）并确认无回归；重点验证 `TASK_ACTIVE -> RECOVERING -> BASE_ACTIVE`。

6. **人工验收**  
   在目标 profile 下至少做 3 次 task 退出，确认 recovery 姿态一致、无额外按键依赖。

### 验收标准（全部满足）

- recovery 不再依赖人工 `n/p/t`
- recovery 姿态可重复且体感稳定
- 双向切换（base->task、task->base）无新增异常
- 项目约束保持不变：仅 `o` 触发 E-STOP

### 回退策略

- 若新目标不稳定：回退 `recovery.z_source/z_name` 到上一个已验证目标（如 `move-ego-0-0`）
- 若目标文件异常：`z_sources.goal` 回退原 `goal_reaching.pkl`
- 回退后必须重新跑一次自测 + 一次人工回归

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
- `TASK_ACTIVE -> RECOVERING -> BASE_ACTIVE`：恢复姿态可重复，不受此前手动 `n/p/t` 影响

## 快速检查清单

- [ ] enter/exit 起点都来自 `state["joint_pos"]`
- [ ] 无 `_last_*_q_target` 作为上肢插值起点
- [ ] BeyondMimic/OmniXtreme 插值时长已与 ASAP 对齐（如需）
- [ ] base->task 与 task->base 均已完成回归
- [ ] 自动 recovery 使用固定 z（如 `move-ego-0-0` 或 `tracking_tpose_step0`），不是继承手动 z
- [ ] 若采用 `n-p-t` 固化方案，自定义 goal pkl 已包含 `tracking_tpose_step0`
- [ ] 全链路无自动 E-STOP（仅 `o` 键触发）

---
name: uhc-policy-adaptation
description: Use when adding a new ONNX policy to universal_humanoid_controller, porting from a reference deploy script, debugging sim2sim instability, headless vs GUI mismatch, or aligning physics/actuator/safety with a baseline repo.
---

# UHC 新策略 / 模型适配

## Overview

在 UHC 中接入新策略时，**框架默认行为**（安全裁剪、仿真节拍、力矩路径）必须与**参考训练/部署假设**一致，否则会出现「参考仓库稳定、UHC 倒地」类问题。本 skill 提供可勾选的核对顺序与常见陷阱。

## When to Use

- 新增 `policy_type`、从论文/官方仓库移植 `deploy_*.py`
- headless 通过但 GUI 失败，或长程（30s+）失稳
- 需要与 ASAP/OmniXtreme/BeyondMimic 等参考实现数值对齐

## When NOT to Use

- 纯算法训练问题（与部署路径无关）
- 仅改 UI/键位，未动控制与物理

## 适配检查表（按顺序）

### A. 物理与节拍（不一致则行为不可比）

1. **MuJoCo 模型**：与参考使用同一 XML 或已 diff 质量、`ctrlrange`、关节顺序（`qpos[7:]` 与参考 `dof` 顺序一致）。
2. **仿真步长**：`simulate_dt` × `steps_per_control` = 策略控制周期（如 50Hz → 0.02s）；与参考 `decimation` 一致。
3. **力矩限幅**：优先使用 XML `actuator_ctrlrange` 作为 `effort_limit`；与参考打印的 hip/knee 限幅核对。

### B. 策略特有动力学（从参考逐行抄）

1. **电机模型**：包络（X1/X2/Y1/Y2）、摩擦（Fs/Fd/Va）与参考**同维度、同索引**；未做长程验证前不要「按 URDF 重排」参考列表。
2. **摩擦施加位置**：若在参考里是 **每个物理子步**更新，UHC 须在 `write_action` 的 substep 循环内减摩擦，而非仅用控制周期初值。
3. **FM / 扩散类策略**：若 ONNX 有 `initial_noise`，必须为高斯噪声且维数正确，禁止长期用全零。

### C. 观测与参考动作

1. 关节顺序：BeyondMimic motionlib ↔ URDF 用 `JointMapper`；残差网络若要求 BM 序，在 `_build_residual_obs` 内显式转换。
2. 参考帧索引：与参考一致（例如 `step_count+1` 取下一帧）。
3. 观测噪声：若参考对 `ang_vel` 等加了噪声且训练分布依赖，在对比实验中单变量启用；**不要默认假设「无噪声更稳」**。

### D. 框架安全层（高频根因）

1. **`SafetyGuard.clip_action`**：将目标关节角限制在 `robot_cfg.limits`。高动态、贴地、大膝角动作常需**短时超出 URDF 保守边界。**
   - **症状**：无裁剪长程稳定，有裁剪在数百步内倒地；或膝关节/踝目标被卡在边界附近发抖。
   - **做法**：策略若已有包络反解 + `ctrl` 限幅，在策略 YAML 设 `skip_position_clip: true`，并实现 `BasePolicy.skip_position_clip()` 返回 True；`PolicyRunner` 仅在 `TASK_ACTIVE` 尊重该标志。
2. **`safety_min_height`**：地面动作需策略级覆盖为 `0.0` 或足够低，避免假阳性 E_STOP。

### E. 验证方法

1. 最小复现：无 PolicyRunner，仅 `OmniXtremePolicy` + `MujocoBackend` 或等价循环，长程对比参考。
2. 单变量：先关掉弹性绳、再开关 `clip_action`，打印 `pelvis_z` 曲线。
3. 与 **selftest-reality-alignment** skill 协同：自测须与交互运行同配置、同节拍、同子步。

## 与参考代码的对应关系

| 参考常见形态 | UHC 落点 |
|--------------|----------|
| `deploy_mujoco.py` 主循环 | `PolicyRunner._step` + `MujocoBackend.write_action` |
| 无 `clip` 关节目标、仅 `ctrl` 限幅 | 勿叠加 URDF `clip_action`，除非明确需要 |
| 配置 `noise_scales` | 策略或观测 builder 可选对齐 |

## 已适配策略的经验索引

| 策略 | 关键经验 | 详情文档 |
|------|----------|----------|
| OmniXtreme | `skip_position_clip: true`（自有包络裁剪优先）；`safety_min_height: 0.0`；actuator friction per-substep | `research/omnixrtreme_uhc_adaptation.md` |
| BFM-Zero | 29-DOF 与 UHC 完全对齐（identity mapper）；`action_rescale=5`；obs 4 帧历史 roll 顺序；latent z 通过 `set_z()` 注入；`skip_position_clip: false`（deploy 代码自己做 `np.clip`，与 SafetyGuard 一致） | `research/m4_2_bfm_zero_vs_host.md` |

## 维护说明

新增策略类型时：**在策略 YAML 中显式写出** `skip_position_clip`、`safety_min_height`、以及任何与框架默认冲突的项；并在 `research/` 或 PR 说明中记录一条「与参考差异表」，便于下次模型迭代。

**base_policy 扩展**：使用 `PolicyRunner._create_base_policy()` 根据 `policy_type` 动态加载。新增 base 策略时需：
1. 在 `_create_base_policy` 中增加分支
2. 实现 `get_upper_body_home()` 返回上肢归位姿态（替代 AsapLoco 的 `upper_body_ref`）
3. 在 `_handle_cmd` 中用 `hasattr` 分发策略特定键位

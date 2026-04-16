# OmniXtreme → UHC 适配复盘（2026-04）

本文记录将 [OmniXtreme](https://github.com/Perkins729/OmniXtreme) 接入 `universal_humanoid_controller`（UHC）时的配置对齐、排障过程与**已验证根因**，供后续同类高动态策略（FM + Residual、外部参考动作）复用。

## 1. 结论摘要

| 类别 | 要点 |
|------|------|
| **根因（GUI/交互路径倒地）** | `SafetyGuard.clip_action()` 将关节目标裁剪到 `robot_cfg.limits` 的 URDF 位置上下界；高动态动作需要短时超出这些边界，裁剪后 PD 跟踪与策略训练分布不一致，约数百步后失稳。修复：`skip_position_clip: true` + `BasePolicy.skip_position_clip()` / `PolicyRunner` 条件跳过裁剪。 |
| **必须对齐（否则行为完全不同）** | MuJoCo XML（质量、碰撞、actuator `ctrlrange`）、`simulate_dt` 与 `steps_per_control`（参考 decimation）、per-substep 摩擦模型、FM 的 `initial_noise`、actuator 包络 X1/X2/Y1/Y2 与参考**逐索引一致**（含参考里「非 URDF 语义顺序」的列表，见下）。 |
| **已排除为主要根因** | action_scale / PD 四位小数截断（影响 <0.02% 力矩）、纯 headless 与「参考直启」初始姿态差异（单独测试仍稳定）、`base_ang_vel` 观测噪声缺失（单独加入噪声仍稳定）。 |

## 2. 参考实现 vs UHC 对齐清单

1. **物理世界**：使用与参考相同的 `no_hand.xml` 等价物（UHC：`g1_29dof_omnixrtreme.xml`），核对总质量、`ctrlrange`、关节顺序（`qpos[7:]` 与参考一致）。
2. **控制节拍**：参考 `decimation=5`、`timestep=0.02/5=0.004` → UHC `simulate_dt: 0.004`，`steps_per_control=5`，主循环 50Hz。
3. **力矩路径**：包络反解限位 `_apply_actuator_model`；摩擦在 `MujocoBackend.write_action` **每个物理子步**用当前 `dq` 计算，而非单步近似。
4. **Flow Matching**：Base ONNX 若含 `initial_noise` 输入，须为 `N(0,1)` 维数匹配，不可用全零。
5. **策略级安全**：OmniXtreme 含贴地动作，`safety_min_height: 0.0` 避免骨盆高度误触发 E_STOP。
6. **框架层安全**：高动态策略若自带包络/力矩限幅，**勿再用 URDF 位置裁剪**；在策略 YAML 中显式 `skip_position_clip: true`。

## 3. 数值验证方法

- 脚本：`universal_humanoid_controller/scripts/debug_omnixrtreme_audit.py`（与 `conda` 环境中 `mujoco` 一致的环境运行）。
- 扩展实验（历史排查用）：对比「无 `clip_action`」与「有 `clip_action`」长程（如 2000 步）高度轨迹；后者在约 400–500 步出现持续低重心与倒地，前者稳定。

## 4. 经验教训（给后续模型适配）

1. **框架默认不等于策略假设**：`SafetyGuard.clip_action` 对「行走 / 模仿」可能合理，对「竞技体操式」高动态策略会破坏策略输出；新策略类应显式声明是否跳过位置裁剪。
2. **参考仓库的常量列表顺序**：若参考在注释中写「urdf order」但实际与 MuJoCo `qpos` 顺序一致即可；勿在未做长程对比前「纠正」参考里的包络表顺序（可能与训练分布绑定）。
3. **先长程 headless，再 GUI**：排除渲染后，优先用同一 `PolicyRunner` 逻辑或最小复现脚本做 40s+ 测试，再查 viewer、弹性绳等附加项。
4. **弹性绳（elastic band）**：默认开启时改变等效动力学；高动态任务建议关闭后再验策略本身（与参考无绳部署对齐）。

## 5. 相关代码与配置（UHC）

- `uhc/core/policy_runner.py`：`clip_action` 与 `skip_position_clip` 分支。
- `uhc/policies/base_policy.py`：`skip_position_clip()`。
- `config/policies/omnixrtreme.yaml`：`safety_min_height`、`skip_position_clip`。
- `uhc/policies/omnixrtreme.py`：观测、包络、摩擦参数来源说明。

## 6. Agent Skill

排查与适配流程已提炼为 Cursor skill：**`uhc-policy-adaptation`**（见仓库 `.cursor/skills/uhc-policy-adaptation/SKILL.md`），新增 ONNX 策略接入时应先阅读并勾选其中检查项。

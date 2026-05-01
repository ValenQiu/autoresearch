# OmniXtreme Loopback Deployment Distilled

> 目的：记录 OmniXtreme 在 UHC `sim2real mock` 中 task 接管后早期倒地的部署级调查结论。
> 本文不是论文总结；只保留能决定下一步怎么 debug / 怎么改代码的工程事实。

## 1. 当前症状

最新 loopback 日志显示，`BASE_ACTIVE -> TASK_ACTIVE` 已经能完成：

- task tick 0：`tilt≈1.8deg`、`z≈0.77`、`qerr_max≈0.14`，入口姿态可接受。
- task tick 25：`tilt≈15deg`、`qerr_max≈0.6`，已出现 first divergence。
- task tick 80+：踝 roll / pitch 关节开始越过 URDF 限位，`residual_guard` 归零 residual。
- task tick 100+：高度下降、姿态接近倒地，FM 单独运行后发散。

结论：**guard 归零不是第一根因**。它是失稳后的放大器。第一根因必须在 task tick 0-25 的 action / q_target / tracking 链路中找。

## 2. 已证伪或降级的假设

| 假设 | 当前状态 | 依据 |
|---|---|---|
| upper qerr gate 没过导致 entry OOD | 降级 | gate 可在 2.5s pass，tick 0 qerr 可接受 |
| waist pitch qerr 卡住导致不能进 task | 已修复 | waist hold + arm-only qerr gate 后可进入 TASK_ACTIVE |
| `residual_guard_pos_margin=0.08` 过早压 residual 是第一根因 | 降级 | margin 调为 0 后，tick 25 仍先发散；tick 80 后 guard 才归零 |
| native actuator / friction 常量与 UHC 不一致 | 已证伪 | `X1/X2/Y1/Y2/Fs/Fd/Va` 与 native `deploy_mujoco.py` 数组逐项一致 |
| action_scale 大偏差 | 已证伪 | UHC YAML 与 native `ACTION_SCALE` 最大差约 `4.6e-5` |

## 3. Native Deploy vs UHC 当前关键差异

| 维度 | Native `/home/qiulm/sources/OmniXtreme/deploy_mujoco.py` | UHC 当前 |
|---|---|---|
| 初始状态 | 直接把 MuJoCo root/joints 设置到 motion frame 0 | BFM recovery 后，upper interp，再进入 task |
| residual gain | `RESIDUAL_GAIN` 环境变量默认 `1.0` | `residual_gain: 0.35` |
| q target slew | 无额外 slew limiter | `q_target_slew_rate_rad_s: 6.0` |
| residual guard | 无 | `residual_guard_enabled: true` |
| URDF position clip | 无框架级 URDF clip；仅 envelope + torque limit | `skip_position_clip: true`，已跳过 `SafetyGuard.clip_action` |
| 执行器 | native MuJoCo 内部 PD + per-substep friction | loopback: UHC LowCmd -> DDS bridge -> MuJoCo PD |

最值得优先验证的是：`residual_gain=0.35` 和 `q_target_slew=6.0` 是否把 early task 闭环带离 native 分布。

## 4. First Divergence Debug 口径

不要只看 `tilt` / `qerr_max` 标量。每次复现必须记录：

- `qerr_top5 = q_target - q_actual`
- `raw_top5`
- `base_action_top5`
- `res_action_top5`
- `envelope_delta = q_target_after_envelope - q_target_pre_envelope`
- `slew_delta = q_target_after_slew - q_target_before_slew`
- `guard = scale / s_lim / s_vel / s_z`

判读规则：

| 现象 | 判断 |
|---|---|
| native 与 UHC sim2sim 的 `q_target` 已分叉 | policy obs / action / history / UHC-only stabilizer 问题 |
| UHC sim2sim 与 loopback 的 `q_target` 一致，但 `q_actual` 分叉 | bridge / DDS / friction / contact / timing 问题 |
| `slew_delta` 在 tick 0-25 大量命中下肢 | slew limiter 可能破坏 dynamic phase |
| `base_action` 已异常但 residual 正常 | FM / history / initial_noise / command_obs 问题 |
| `res_action` 大但被 gain/guard 压小 | residual gain / guard 策略问题 |

## 5. 单变量 A/B 矩阵

按顺序执行，禁止一次改多个变量：

| 组别 | 改动 | 目标 |
|---|---|---|
| A0 | 当前配置 | 复现 first divergence tick 和 top joints |
| A1 | `residual_gain: 1.0` | 对齐 native residual 强度 |
| A2 | `q_target_slew_rate_rad_s: 0.0` | 验证 slew 是否导致下肢目标滞后 |
| A3 | `residual_guard_enabled: false` | 验证 guard 是否只是二阶放大器 |
| A4 | `residual_gain=1.0` + `q_target_slew=0.0` + `residual_guard=false` | native-like policy output 对照 |

每组必须记录：

- first `tilt > 15deg` tick
- first `qerr_max > 0.5` tick
- first `z < 0.6` tick
- top-5 qerr joints at tick 0 / 25 / 50
- envelope / slew 是否命中同一批关节

## 6. 与 ASAP / MTC / RoboJuDo 的部署原则对照

| 经验 | 对 Omni 当前问题的含义 |
|---|---|
| ASAP Loco/Mimic 切换依赖 RL controller，而不是纯 PD 回正 | task 接管后不能让 residual 被安全层切掉后只剩 FM/PD 硬撑 |
| MTC 复盘指出 standby 纯 PD 无动态恢复能力 | 如果 Omni 输出被 slew/guard 削弱，等价于把高动态任务降级成不完整 PD 跟踪 |
| RoboJuDo 强调 `passive -> recovery -> task` 且必须有稳定门 | BFM recovery 后的 root/contact/foot preload 也必须被量化，而不是只看 upper qerr |
| UHC `selftest-reality-alignment` 要求同路径 | debug 脚本必须覆盖 PolicyRunner + profile + bridge，不应只测裸 policy |

## 7. 下一步实现状态

已在 UHC `OmniXtremePolicy` audit 中增加 top-k 诊断：

- `[OmniXtremePolicy][audit_top]`
- `[OmniXtremePolicy][audit_ctrl]`

预期下一次 loopback 日志能直接回答：

1. tick 0-25 最先发散的是哪个关节。
2. 发散来自 `base`、`residual`、`envelope`、还是 `slew`。
3. guard 在 first divergence 前是否已经介入。

# OmniXtreme Loopback Deployment Distilled

## Goal

Pin down the first divergence in OmniXtreme sim2real mock / loopback runs without adding stability patches before evidence exists.

## Current Judgment

The latest log already shows the entry gate is not the first root cause:

- `tick=0`: `tilt=1.81`, `qerr_max=0.138`, gate passes.
- First clear divergence happens after task takeover, around `tick≈25`:
  - `tilt=15.73`
  - `qerr_max=0.611`
  - `qd_max=4.52`
- Later ankle roll/pitch limit violations are likely downstream of instability, not the first cause.

## Verified Native vs UHC Differences

These are real code-path differences that should be tracked first:

- Native `deploy_mujoco.py` uses `RESIDUAL_GAIN=1.0` by default.
- UHC `config/policies/omnixrtreme.yaml` currently uses `residual_gain: 0.35`.
- Native has no `q_target_slew_rate_rad_s`; UHC currently uses `6.0` rad/s.
- Native has no `residual_guard`; UHC has a residual attenuation guard enabled.
- Native initializes from motion frame 0 full root/joint state.
- UHC enters from a BFM recovery pose, so root/contact/waist/foot state may differ even when `qerr` is small.

Current UHC config values that matter:

- `residual_gain: 0.35`
- `q_target_slew_rate_rad_s: 6.0`
- `residual_guard_enabled: true`
- `audit_enabled: true`
- `task_entry_stabilize_ticks: 25`
- `safety_min_height: 0.0`
- `skip_position_clip: true`

## Diagnostic Coverage Added in UHC

Implemented in `uhc/policies/omnixrtreme.py`:

- `audit_enabled` now prints top-k joint diffs instead of only scalar summaries.
- Audit now records:
  - `raw`
  - `base`
  - `res`
  - `q_target_pre_envelope`
  - `q_target_post_envelope`
  - `q_target_pre_slew`
  - `q_target`
  - `env_clip`
  - `slew_clip`
  - residual guard detail (`position`, `velocity`, `height` contribution)
- Optional `audit_csv_path` writes the same data as JSON-array columns for offline compare.

Implemented in `scripts/compare_omni_deploy_obs.py`:

- Existing native-deploy-vs-UHC single-frame math compare is preserved.
- Added audit CSV comparison mode:
  - compare multiple CSV logs at a chosen tick
  - print scalar deltas and top-k vector diffs
  - baseline-first workflow for native / sim2sim / loopback runs

## Working Hypothesis Order

Do not add more stabilization until these are tested in order:

1. Residual gain mismatch is amplifying divergence too early.
2. Slew limiter is lagging task targets enough to change the policy trajectory.
3. Entry-state distribution differs materially between native motion-frame-0 start and BFM recovery entry.
4. Loopback executor / contact path introduces additional lag or state skew.

## A/B Matrix

Run these one at a time, keeping everything else unchanged:

- `A0`: current config, reproduce first divergence tick.
- `A1`: set `residual_gain=1.0`, keep slew and guard unchanged.
- `A2`: set `q_target_slew_rate_rad_s=0.0`, keep residual gain and guard unchanged.
- `A3`: set `residual_guard_enabled=false`, keep residual gain and slew unchanged.
- `A4`: native-like combo: `residual_gain=1.0`, no slew, no residual guard, envelope/friction only.

Record for each run:

- first `tilt > 15°` tick
- first `qerr_max > 0.5` tick
- top offending joint
- minimum pelvis `z`
- whether low-height guard triggered

## Compare Workflow

### 1. Single-frame math compare

Use the existing script for deploy math vs UHC observation assembly:

```bash
python3 scripts/compare_omni_deploy_obs.py --frame 0 --assert
```

### 2. Audit CSV compare

With audit CSV enabled in the policy config, compare multiple runs at the same tick:

```bash
python3 scripts/compare_omni_deploy_obs.py \
  --audit-csv native.csv sim2sim.csv loopback.csv \
  --audit-labels native sim2sim loopback \
  --audit-tick 25
```

If `--audit-tick` is omitted, `--frame` is reused as the tick selector.

## What Is Already Ruled Out

These should not be treated as first-order causes unless new evidence appears:

- gate failure at task entry
- constant-array mismatch in the current observation assembly
- large action-scale error by itself
- a purely larger guard margin as the sole explanation

## Open Questions

The next evidence to collect should answer:

- Which joint first diverges from native-like behavior?
- Does the divergence start in `raw`, `base`, `res`, or only after envelope / slew?
- Is the first mismatch visible in native-like `q_target_pre_slew`, or only after the executor / contact path?
- Does loopback differ from sim2sim before the robot visibly destabilizes?

## Linkage to Existing Principles

This follows the deployment principles already observed in other high-dynamic controllers:

- policy output should not be blindly overridden by safety layers
- task switch / handover needs a stable gate
- controller, environment, and policy layers should be compared separately
- selftests or diagnostics must follow the real execution path, not a simplified surrogate

## Repository Notes

- `OmniXtreme` reference path: `/home/qiulm/sources/OmniXtreme/deploy_mujoco.py`
- UHC policy path: `/home/qiulm/sources/universal_humanoid_controller/uhc/policies/omnixrtreme.py`
- UHC compare script: `/home/qiulm/sources/universal_humanoid_controller/scripts/compare_omni_deploy_obs.py`
- UHC policy config: `/home/qiulm/sources/universal_humanoid_controller/config/policies/omnixrtreme.yaml`

## Next Step

Run `A0` with audit CSV enabled, then compare `A0` against `A1` and `A2` before touching any stability patch.
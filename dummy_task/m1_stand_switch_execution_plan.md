# M1 Execution Plan: Stand-Switch Pipeline Bring-up

## Objective

First milestone is strictly:
- Boot in `PASSIVE`
- Trigger recovery/base control (`standby_controller`) to reach standing posture
- Switch to task policy safely
- Support deterministic switch-back and emergency stop

This milestone is sim2sim-first (keyboard input only).

## Fixed Context

- Branches:
  - `whole_body_tracking@autoresearch`
  - `motion_tracking_controller@autoresearch`
- Robot: `G1 29DoF`
- Base policy format: `ONNX`
- Input implementation priority: `keyboard -> xbox -> unitree_remote`
- Runtime input selection contract:
  - Startup must pass `--input_source` with one of: `keyboard | xbox | unitree_remote`
  - Exactly one input source is active for one runtime process
  - For M1, fixed to `--input_source keyboard`

## Codebase Roots

- Training:
  - `/home/qiulm/sources/whole_body_tracking`
  - Docker bootstrap: `/home/qiulm/sources/whole_body_tracking/docker/docker_run.sh`
- Deployment:
  - `/home/qiulm/sources/motion_tracking_controller`
  - Docker bootstrap: `/home/qiulm/sources/motion_tracking_controller/docker_run.sh`
- ASAP references:
  - `/home/qiulm/sources/ASAP`
  - `/home/qiulm/sources/ASAP/sim2real`

## Implementation Checklist (ordered)

1. Runtime state machine scaffold
   - Add states: `PASSIVE`, `BASE_ACTIVE`, `TASK_ACTIVE`, `E_STOP`
   - Add events: `ACTIVATE_BASE`, `ACTIVATE_TASK`, `SWITCH_TO_BASE`, `E_STOP`, `RESET_TO_PASSIVE`
   - Add guards: `observer_healthy`, `comms_healthy`, `joint_limits_ok`, `base_stable`, `target_posture_reached`

2. Base policy contract (M1 terminology unified)
   - In M1 runtime semantics:
     - `base policy` = `recovery controller` = `standby_controller`
   - Startup and BASE_ACTIVE path should prioritize controller-level recovery safety.
   - Optional ONNX base model can be kept only for compatibility checks (not required for base control ownership).

3. Keyboard input router (ASAP-style trigger semantics)
   - Map keypresses to normalized runtime events
   - Keep trigger table configurable in one file
   - Ensure input is edge-triggered (debounced) to avoid repeated transitions
   - Wire startup arg parser to enforce single-source binding (`--input_source keyboard` in M1)

4. Backend abstraction integration (sim first)
   - Implement/extend `MujocoBackend` adapter with:
     - `read_observation`
     - `write_action`
     - `get_robot_status`
     - `set_control_mode`
   - Enforce startup `PASSIVE` mode with zero policy torque output

5. Policy handover logic
   - Block `ACTIVATE_TASK` unless:
     - target posture reached for N cycles
     - stability and safety checks pass
   - On task policy failure:
     - immediate fallback to `BASE_ACTIVE`
   - On severe fault:
     - force `E_STOP`

6. Telemetry and logs
   - Log transition timestamps, source event, guard status
   - Log every policy switch reason and fallback cause
   - Log structured reject info (`reject_code`, `reject_reason`)
   - Persist one session-level run summary

## Acceptance Tests (must pass)

1. Passive boot test
   - Start runtime, verify no active policy output.

2. Recovery-to-stand test
   - Trigger base/recovery controller (`standby_controller`).
   - Verify robot reaches standing posture and keeps it for N cycles.

3. Guarded task-switch test
   - Try activate task before standing reached -> must reject with explicit reason.
   - After standing reached -> switch succeeds.

4. Switch-back test
   - Trigger return to base/recovery controller from task policy -> deterministic success.

5. E-stop preemption test
   - Trigger emergency stop at each active state -> immediate `E_STOP`.

## Test Entry Rule (M1)

- Default test entry must be `ros2 launch motion_tracking_controller runtime_m1.launch.py`.
- Model/policy source should be managed by `profile_json` config file (e.g. `runtime_m1_valen_asap_base_bm_task.json`) instead of long CLI model arguments.
- `python3 scripts/runtime_m1.py ...` is fallback-only for debugging and must not be the primary validation path.
- M1 verification should prioritize keyboard interaction path under launch runtime.

## Startup Anti-Fall Support (ASAP-style adaptation)

Background:
- Current M1 has no get-up policy. If simulator starts from unstable posture and `walking_controller` is configured too early, robot may collapse immediately.

Implemented approach (current code path):
- Add MuJoCo startup support mode in launch/runtime chain:
  - `startup_support_mode:=m1_standby`
  - `spawn_inactive_controllers:=false`
- In `m1_standby` mode, startup active controllers become:
  - `state_estimator`
  - `standby_controller`
- `walking_controller` is not configured at startup stage in this mode.
- Runtime keeps keyboard-first mode and uses `]` to enter `BASE_ACTIVE` path.
- Runtime safety lock: if user passes `startup_support_mode:=m1_standby` with
  `spawn_inactive_controllers:=true`, runtime forces it back to `false` to
  prevent regressions caused by inactive-controller startup races.

Why this works:
- It avoids the early `walking_controller` configuration failure path (`joint_names` metadata mismatch) from blocking safe startup.
- It shifts boot behavior toward a "support-first, then release/switch" flow similar to ASAP's safety intent.

Current limit:
- This is controller-level startup support, not a MuJoCo force-level elastic band.
- A true elastic-band/hoist force (`xfrc_applied`) would require simulator-force injection integration in the MuJoCo loop, which is not yet in this M1 patch.

## Current Validation Snapshot

Validated in container smoke run (`ros2 launch` default path):
- `runtime_m1.launch.py` starts `runtime_m1.py` successfully.
- Auto-started MuJoCo command includes:
  - `startup_support_mode:=m1_standby`
  - `spawn_inactive_controllers:=false`
- Startup no longer requires configuring `walking_controller` immediately.
- Runtime enters `PASSIVE` and keeps keyboard event loop alive.
- User-confirmed stable startup log signature:
  - `startup_support_mode:=m1_standby`
  - `spawn_inactive_controllers:=false`
  - This should be treated as required baseline for M1 startup validation.

## TASK->BASE Switch Safety Baseline (updated)

Observation:
- TASK->BASE fall issue was not caused by rollback/removal of decel window.
- Decel window remained active; prior default (`10` cycles at `100Hz`) was too short for dynamic handover.

Mitigation baseline (current runtime):
- `task_to_base_blend_cycles:=80` (default)
- `task_to_base_speed_gate_mps:=0.35` (TF speed gate; if unavailable, runtime degrades gracefully)
- `task_to_base_switch_max_wait_cycles:=300`
- `task_to_base_estop_min_z:=0.20` (near-fall trigger during decel window -> force E_STOP)

Expected behavior:
- `[` in `TASK_ACTIVE` enters decel/guard window.
- Runtime waits for blend window and low-speed gate (or timeout) before switching to BASE.
- If base height approaches fall threshold during the decel window, runtime preempts to E_STOP.

Known failure mode (still expected):
- If `task_model_path` points to `models/base/model_6600.onnx`, `walking_controller` configuration can still fail later with:
  - `OnnxPolicy: 'joint_names' not found in model metadata`
- This is model compatibility issue (task ONNX schema), not startup support mode failure.

## Blocking Conditions

- Recovery ONNX model output semantics mismatch with deployment action space
- Observation schema mismatch between base and task policy
- Unstable or undefined backend control mode transition behavior

## Exit Criteria

M1 is complete only when all acceptance tests pass in sim2sim and logs are reproducible.

## Project Progress Sync (2026-04-13)

Synchronized scope in this round:
- Runtime entry is now profile-driven by default (`ros2 launch motion_tracking_controller runtime_m1.launch.py` + default `profile_json`).
- Tick-limit behavior aligned with runtime usage: `max_ticks=none` means infinite run; positive values are test-only.
- Startup anti-fall baseline is locked and verified in logs:
  - `startup_support_mode:=m1_standby`
  - `spawn_inactive_controllers:=false`
  - runtime safety lock enforces the above pair to avoid regression.
- TASK->BASE path remains decel-window based (not removed) and was upgraded with safer switch guards:
  - longer blend window (`task_to_base_blend_cycles`),
  - speed gate before switch,
  - max-wait fallback,
  - near-fall early `E_STOP` guard.

Current M1 status:
- `PASSIVE -> BASE_ACTIVE -> TASK_ACTIVE` and `E_STOP` paths are available in launch-first workflow.
- Startup stability issue is confirmed fixed by user with expected launch signature.
- TASK->BASE anti-fall behavior has been hardened and is in verification loop.

Related baseline card:
- `dummy_task/m1_stability_baseline_card.md`

## M1 Gap Check (pending items)

尚未闭环/需要继续验证的目标：

1. 【下一任务】参考 ASAP，在 `standby -> task` 与 `task -> standby` 过程中实现上肢关节跨策略映射 + 3 秒实时插值，并在终端打印插值进度条；task 结束后自动插值回 base 姿态并自动切回 `standby_controller`，形成闭环。
2. 文档定义的 backend 统一抽象接口仍偏草案，尚未完整工程化落地。
3. 结构化持久化日志（JSON/CSV）还可补齐，便于长期回归。

## Current Task Check (latest)

- 已完成：`task policy` 运行期异常注入与自动回落 `BASE` 代码路径已实现，并新增 `selftest_m1_task_fault_fallback.sh` 验收脚本（容器内 PASS）。
- 待确认：在你的实际运行环境中，需再确认一次“异常注入后稳定回落 BASE 且不中断进程”。

## Project Handover Snapshot (2026-04-14)

本节用于跨机器/新 Agent 续做的最小完整上下文。

### A. 本轮已落地能力

- 执行层上肢插值通道已打通：
  - runtime 发布 `/runtime_m1/upper_body_blend_cmd`（`Float64MultiArray`）
  - `walking_controller` 订阅并在 `MotionCommandTerm` 中融合到 ONNX 关节命令
- `BASE->TASK` 与 `TASK->BASE` 路径都保留插值阶段；`TASK->BASE` 在窗口期抑制 `task_policy.step()`。
- controller switch 增加更稳健的 strict 两步重试（deactivate->activate）。
- 新增 trace 诊断链路（关键）：
  - runtime 支持 `trace_enable/trace_output_jsonl/trace_stride/trace_joint_names_csv`
  - 采集状态机、事件、切换结果、拒绝码、/tf 速度与高度、/joint_states、blend 命令快照、策略输入输出摘要。
- 新增专项自测：
  - `scripts/selftest_m1_trace_diag.sh`
  - `scripts/m1_trace_diag_events.json`
  - `SELFTEST_MODE=trace_diag bash scripts/selftest_m1.sh`

### B. 本轮关键诊断结论（基于 trace_diag）

- `PASSIVE -> BASE_ACTIVE -> TASK_ACTIVE -> BASE_ACTIVE` 转换链路可跑通。
- 最近一次 trace_diag 报告显示：
  - 三段 transition 均 `OK`
  - `TASK->BASE` 切后短窗口（默认 200 ticks）最小 `pelvis_z` 正常
  - 但后段日志仍可出现 `base low height detected`（晚发波动，当前诊断窗口尚未覆盖）
- `BASE->TASK` 插值“看起来不动”的根因已确认：
  - `base_to_task_max_delta=0.000000`
  - 即 task 上肢目标与 standby 上肢目标几乎一致，属于配置目标问题，不是插值通道失效。

### C. 仍待收敛问题（下一 Agent 优先级）

1. 扩展 trace 诊断窗口：
   - 从切后 200 ticks 扩到 500~800 ticks；
   - 增加“晚发低高度事件”判定与摘要输出。
2. 给 `task_upper_body_init_pose` 提供“可见差值”自测配置（只用于诊断）：
   - 至少 shoulder/elbow 关节与 standby 保持明显差值；
   - 验证 base->task 插值确实产生关节变化。
3. 收敛 TASK->BASE 切换门禁：
   - 当前代码支持 `task_to_base_speed_gate_hold_cycles`；
   - 需确保运行时实际生效参数与 profile 一致（以 runtime 启动日志为准）。

### D. 新机器接续的第一条命令

在工作空间根目录执行：

```bash
cd ~/colcon_ws
SELFTEST_MODE=trace_diag bash src/motion_tracking_controller/scripts/selftest_m1.sh
```

结束后保留两类产物：
- `/tmp/m1_trace_diag.*.jsonl`
- `/tmp/m1_trace_diag.*.log`

并用它们做下一轮根因分析。

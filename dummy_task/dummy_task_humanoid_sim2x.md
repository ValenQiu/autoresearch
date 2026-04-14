# Dummy Task: Humanoid Sim2Sim + Sim2Real Unified Deployment Pipeline

## 1) Task Goal

Build a robust deployment framework for humanoid motion policies with one unified policy-layer logic for:
- Sim2Sim (MuJoCo or other simulators)
- Sim2Real (Unitree hardware over ethernet first, extensible later)

The only difference between sim and real should be backend I/O adapters, not policy orchestration logic.

## 2) References and Scope

- Training backbone: BeyondMimic training repo (`whole_body_tracking`)
- Deployment backbone: BeyondMimic deployment repo (`motion_tracking_controller`)
- Pipeline inspiration: ASAP (`base_sim` + keyboard-triggered base policy and policy switching)
- Recovery baseline option: HoST (multi-posture standing-up controller)

## 2.1) Project Context (confirmed)

- Branches:
  - `whole_body_tracking`: `autoresearch`
  - `motion_tracking_controller`: `autoresearch`
- Robot:
  - Unitree `G1` with `29DoF`
  - DoF and all low-level config must stay consistent with BeyondMimic configs.
- Base policy model format:
  - `ONNX` (same deployment contract as BeyondMimic)
- Input implementation priority:
  - `keyboard` -> `xbox` -> `unitree_remote`
- Runtime input selection:
  - Startup script must expose one explicit `input_source` argument.
  - Exactly one input source is active per run (`keyboard` or `xbox` or `unitree_remote`).
  - This is configured similarly to how sim2real startup specifies robot IP/interface.
- Sim2Real comm layer:
  - Keep consistent with current BeyondMimic deployment stack.

## 2.2) Local Paths and Environments (confirmed)

- BeyondMimic training:
  - path: `/home/qiulm/sources/whole_body_tracking`
  - env bootstrap: `/home/qiulm/sources/whole_body_tracking/docker/docker_run.sh`
- BeyondMimic deployment:
  - path: `/home/qiulm/sources/motion_tracking_controller`
  - env bootstrap: `/home/qiulm/sources/motion_tracking_controller/docker_run.sh`
- ASAP training:
  - path: `/home/qiulm/sources/ASAP`
  - conda env: `hvgym`
- ASAP deployment:
  - path: `/home/qiulm/sources/ASAP/sim2real`
  - conda env: `robo_deploy`

## 3) Functional Requirements

### R1. Unified runtime state machine

States:
1. `PASSIVE`: no policy output, robot in safe passive/standby mode.
2. `BASE_ACTIVE`: base recovery policy controls robot to reach and hold target posture.
3. `TASK_ACTIVE`: motion-tracking policy controls robot.
4. `E_STOP`: emergency stop with highest priority.

Transitions:
- `PASSIVE -> BASE_ACTIVE`: explicit trigger (keyboard/gamepad/remote).
- `BASE_ACTIVE -> TASK_ACTIVE`: explicit trigger + safety gate checks.
- `TASK_ACTIVE -> BASE_ACTIVE`: operator trigger or runtime fallback.
- `* -> E_STOP`: any safety trigger.
- `E_STOP -> PASSIVE`: manual reset sequence.

### R2. Base policy integration (recovery-only)

Use a single base policy mode:
- `recovery_to_target_posture`: regardless of initial posture, drive robot to a target posture and maintain it.

Current simplified target posture:
- `standing`

Requirements:
- Base policy has deterministic activation trigger.
- Base policy exposes `is_stable()` and `is_ready_for_task_switch()` signals.
- Base policy exposes `target_posture_reached()` signal for explicit gate checks.
- Task policy can only activate when base policy reports safe-ready.

### R3. Trigger and input abstraction

Operator commands must be abstracted as normalized events:
- `ACTIVATE_BASE`
- `ACTIVATE_TASK`
- `SWITCH_TO_BASE`
- `E_STOP`
- `RESET_TO_PASSIVE`
- optional velocity/heading commands

Input devices (same event schema):
- keyboard
- Xbox controller
- Unitree remote

Runtime constraint:
- Only one input source can be bound at startup (`input_source`), no multi-source mixing in one process.

### R4. Sim/real backend abstraction

Create backend interface:
- `read_observation()`
- `write_action(action)`
- `get_robot_status()`
- `set_control_mode(mode)`

Implementations:
- `MujocoBackend` (sim2sim)
- `UnitreeBackend` (sim2real)

Policy manager and state machine must not depend on backend-specific code.

### R5. Safety and fallback

Mandatory checks before `TASK_ACTIVE`:
- estimator valid
- communication healthy
- joint/state bounds valid
- base policy stable for N cycles
- target posture reached for N cycles

Fallback policy:
- If task policy errors or violates safety constraints, auto-fallback to `BASE_ACTIVE`.
- If fallback fails or severe event occurs, force `E_STOP`.

## 4) Non-Functional Requirements

- End-to-end switch latency target: <= 100 ms (base/task switch command to first action frame)
- Runtime loop jitter bounded and logged
- Deterministic startup/shutdown sequence
- Full event/action/state logs for replay and debugging

## 5) Proposed Architecture

Core modules:
- `RuntimeOrchestrator` (main loop)
- `PolicyManager` (base/task policy lifecycle)
- `StateMachine` (mode transitions + guard checks)
- `SafetySupervisor` (hard constraints + fallback rules)
- `InputRouter` (keyboard/xbox/unitree remote adapters)
- `BackendAdapter` (`MujocoBackend`, `UnitreeBackend`)
- `TelemetryLogger` (state transitions, command traces, policy stats)

## 6) Suggested Bring-up Order

Phase A (M1, sim-only first milestone: stand-switch):
1. Build state machine with mock task policy + real recovery base policy entry.
2. Integrate `MujocoBackend` and keyboard input first.
3. Validate `PASSIVE -> BASE_ACTIVE` ("run recovery to standing and hold").
4. Validate controlled `BASE_ACTIVE -> TASK_ACTIVE` handover.
5. Validate `TASK_ACTIVE -> BASE_ACTIVE` rollback and `E_STOP`.

Phase B (real backend onboarding):
1. Integrate `UnitreeBackend` with passive + e-stop + heartbeat checks.
2. Enable recovery base policy only on hardware.
3. Add task policy switch after stability gates.

Phase C (multi-input support):
1. Keyboard adapter first.
2. Xbox adapter.
3. Unitree remote adapter.
4. Validate identical command semantics across all inputs.

## 7) Test Matrix

### T1. State transition tests
- All legal transitions succeed.
- Illegal transitions rejected with explicit reasons.

### T2. Safety tests
- Random communication drop -> fallback or e-stop.
- Policy runtime exception -> fallback to base.
- Invalid observation -> reject task activation.

### T3. Sim2sim parity tests
- Same trigger sequence produces consistent mode transitions and logs.

### T4. Sim2real smoke tests
- Passive boot
- Base recovery activation
- Task activation
- Task->base switch
- Emergency stop

### T6. M1 acceptance (stand-switch first)
- From arbitrary initial sim posture, recovery policy reaches standing posture and holds for N cycles.
- Task policy activation is blocked before `target_posture_reached`.
- After reaching standing posture, task policy can be activated with no unsafe transient.
- Keyboard emergency stop always preempts both policies.

### T5. Input parity tests
- Keyboard/Xbox/Unitree remote produce identical normalized events.

## 8) Deliverables

1. Unified architecture doc + state diagram
2. Backend adapter interface + two implementations
3. Base/task policy switcher and safety supervisor
4. Input adapters (keyboard/xbox/unitree)
5. Automated test suite and log replay tools
6. Deployment playbooks:
   - sim2sim runbook
   - sim2real runbook

## 9) Success Criteria

- Sim2sim and sim2real share same policy orchestration code path.
- Robot starts in `PASSIVE`, only moves after explicit base activation.
- Recovery base policy can safely hand over to task policy.
- Runtime supports emergency stop and deterministic fallback.
- Multi-input command sources are interchangeable at event layer.

## 10) First Milestone Definition (locked)

Milestone name:
- `M1: Stand-switch pipeline bring-up`

What "done" means:
- In sim2sim, startup is `PASSIVE`.
- Operator uses keyboard event to activate recovery base policy.
- Robot reaches standing target posture and remains stable.
- Operator triggers switch to motion tracking policy successfully.
- Operator can switch back to base policy and trigger emergency stop deterministically.

## 11) 项目进度同步（2026-04-13）

M1 当前进展（sim2sim, keyboard-first）：
- 默认入口统一为 `ros2 launch motion_tracking_controller runtime_m1.launch.py`，并通过 `profile_json` 管理模型来源。
- 启动防跌倒基线已锁定：`m1_standby + spawn_inactive_controllers=false`，并在 runtime 侧增加防回退强制保护。
- `max_ticks` 语义已标准化：`none` 表示无限运行，正整数仅用于测试脚本。
- TASK->BASE 切回链路已做强化：
  - 保留并扩展减速窗口，
  - 增加速度门禁与最大等待周期，
  - 增加减速窗口中的近跌倒提前 `E_STOP` 兜底。

阶段结论：
- M1 基本功能已实现，启动稳定性回归问题已闭环。
- 仍在持续验证 TASK->BASE 在高动态场景下的抗跌倒表现，作为 M1 最终收敛项。

## 12) 项目进度同步（2026-04-14，跨机器续做快照）

本轮新增：
- runtime 已支持 trace 证据链采集（状态机/切换事件/关节状态/策略摘要/插值命令）。
- 已新增 `trace_diag` 自测模式与事件脚本，能够复现实验链路：
  - `PASSIVE -> BASE_ACTIVE -> TASK_ACTIVE -> BASE_ACTIVE`
- 已在日志侧明确区分：
  - “controller switch 失败”
  - “switch 成功但切后稳定性失败”

本轮关键结论：
- 切换链路可成功闭环；
- `BASE->TASK` 插值视觉无变化的主因是目标姿态与 standby 几乎一致（配置层问题）；
- `TASK->BASE` 仍可能出现晚发低高度告警，需要扩大 post-switch 诊断窗口进一步归因。

下一步（给新 Agent）：
1. 扩展 trace 自测报告的 post-switch 诊断窗口（建议 500~800 ticks）。
2. 制作“有可见上肢差值”的 task init pose 自测配置，验证插值动作有效性。
3. 继续收敛 TASK->BASE 门禁参数并输出一份可复现实测基线卡。

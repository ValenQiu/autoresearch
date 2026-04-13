# M1 稳定运行基线参数卡

更新时间：2026-04-14  
适用范围：`motion_tracking_controller` 的 M1（sim2sim + keyboard-first）

## 1) 目标

用于固定 M1 当前“可稳定复现”的最小参数集合，避免回退到历史不稳定组合。

## 2) 启动基线（必须满足）

- 启动入口：`ros2 launch motion_tracking_controller runtime_m1.launch.py`
- 配置入口：`profile_json`（默认指向 `runtime_m1_valen_asap_base_bm_task.json`）
- 启动安全模式：
  - `mujoco_startup_support_mode:=m1_standby`
  - `mujoco_spawn_inactive_controllers:=false`
- 防回退锁（runtime 内置）：
  - 若传入 `m1_standby + spawn_inactive_controllers=true`，会被强制改写为 `false`

## 3) 关键参数基线（当前默认）

来自 `config/g1/runtime_m1_valen_asap_base_bm_task.json` 与 launch 默认值：

- `max_ticks: "none"`（无限运行；正整数仅用于测试）
- `control_hz: 100`
- `stable_hold_cycles: 80`
- `task_to_base_blend_cycles: 80`
- `task_to_base_speed_gate_mps: 0.08`（若运行日志仍显示 0.35，表示未加载到最新 profile）
- `task_to_base_speed_gate_hold_cycles: 30`（需连续满足速度门禁才允许切换）
- `task_to_base_switch_max_wait_cycles: 300`
- `task_to_base_estop_min_z: 0.30`

## 4) 启动后日志验收信号（应出现）

- `startup_support_mode:=m1_standby`
- `spawn_inactive_controllers:=false`
- `runtime_semantics: BASE_ACTIVE=standby_controller ... TASK_ACTIVE=walking_controller ...`
- `task_to_base_guard: blend_cycles=80 speed_gate_mps=<期望值> speed_gate_hold_cycles=30 max_wait_cycles=300 estop_min_z=0.30`
- `trace: enable=<true/false> stride=<N> output=<path>`

## 5) TASK->BASE 回切期望行为

- `[` 在 `TASK_ACTIVE` 时先进入减速窗口（不是立即硬切）
- 运行时在窗口内等待：
  - 满足最小窗口周期，且速度门禁通过；或
  - 达到最大等待周期后强制执行切换
- 若窗口内基座高度接近跌倒阈值，提前触发 `E_STOP`

## 6) 禁止回退的高风险组合

- `mujoco_startup_support_mode:=legacy`
- `mujoco_spawn_inactive_controllers:=true`（与 `m1_standby` 同时使用时尤其危险）
- `task_to_base_blend_cycles` 过低（例如 `10`）并直接用于动态场景

## 7) 快速复核命令

```bash
ros2 launch motion_tracking_controller runtime_m1.launch.py
```

若需短测：

```bash
ros2 launch motion_tracking_controller runtime_m1.launch.py max_ticks:=600
```

## 8) 复现失败时优先检查

1. 是否真的走了上述启动基线（先看日志签名）
2. `task_policy` ONNX 是否与 `walking_controller` 元数据兼容（`joint_names` 等）
3. 回切前是否处于高动态工况（速度门禁日志）
4. 是否出现 `controller_switch_failed` 或接口占用告警

## 9) 新增：证据链自测（推荐）

```bash
cd ~/colcon_ws
SELFTEST_MODE=trace_diag bash src/motion_tracking_controller/scripts/selftest_m1.sh
```

输出：
- trace：`/tmp/m1_trace_diag.*.jsonl`
- log：`/tmp/m1_trace_diag.*.log`

诊断重点：
- 三段 transition 是否全部 OK
- TASK->BASE 切换后窗口最小 `pelvis_z`
- `base_to_task_max_delta` 是否接近 0（若是，说明上肢目标与 standby 几乎一致，插值视觉不明显）


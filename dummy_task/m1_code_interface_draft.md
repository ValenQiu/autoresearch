# M1 代码级接口草案（Stand-switch）

本文档给出 `motion_tracking_controller@autoresearch` 的 M1 落地接口草案。  
目标：先在 sim2sim 跑通 `PASSIVE -> BASE_ACTIVE -> TASK_ACTIVE`，并支持回切与急停。

术语统一（M1）：
- `base policy` = `recovery 控制器` = `standby_controller`
- M1 的 BASE_ACTIVE 以控制器切换语义为准；base ONNX 模型在当前实现中仅作可选兼容校验，不作为 base 控制所有权来源

---

## 1) 启动参数接口（必须）

建议统一到一个启动入口（示例：`runtime_main`）：

```bash
runtime_main \
  --backend mujoco \
  --input_source keyboard \
  --base_model_path /abs/path/base_recovery.onnx \
  --task_model_path /abs/path/task_tracking.onnx \
  --config /abs/path/g1_29dof_hist.yaml
```

参数约束：

- `--input_source` 必填，且只能是 `keyboard | xbox | unitree_remote` 之一
- 单进程仅允许一个输入源
- M1 固定 `--input_source keyboard`

---

## 2) 建议文件结构（草案）

> 路径以 `motion_tracking_controller` 为根目录。

```text
include/motion_tracking_controller/runtime/
  runtime_types.hpp
  runtime_config.hpp
  state_machine.hpp
  backend_adapter.hpp
  input_adapter.hpp
  policy_adapter.hpp
  safety_supervisor.hpp
  policy_manager.hpp
  runtime_orchestrator.hpp

src/runtime/
  runtime_config.cpp
  state_machine.cpp
  keyboard_input_adapter.cpp
  input_factory.cpp
  mujoco_backend_adapter.cpp
  unitree_backend_adapter.cpp         # M1 可先 stub
  recovery_base_policy_adapter.cpp
  task_policy_adapter.cpp
  safety_supervisor.cpp
  policy_manager.cpp
  runtime_orchestrator.cpp
  runtime_main.cpp
```

---

## 3) 核心类型定义（C++ 接口草案）

```cpp
enum class RuntimeState {
  PASSIVE,
  BASE_ACTIVE,
  TASK_ACTIVE,
  E_STOP
};

enum class RuntimeEvent {
  ACTIVATE_BASE,
  ACTIVATE_TASK,
  SWITCH_TO_BASE,
  E_STOP,
  RESET_TO_PASSIVE
};

enum class InputSource {
  KEYBOARD,
  XBOX,
  UNITREE_REMOTE
};

struct GuardStatus {
  bool observer_healthy{false};
  bool comms_healthy{false};
  bool joint_limits_ok{false};
  bool base_stable{false};
  bool target_posture_reached{false};

  bool ready_for_task_switch() const {
    return observer_healthy && comms_healthy && joint_limits_ok &&
           base_stable && target_posture_reached;
  }
};
```

---

## 4) RuntimeConfig（参数与校验）

```cpp
struct RuntimeConfig {
  std::string backend;               // mujoco | unitree
  InputSource input_source;          // single source only
  std::string base_model_path;       // optional ONNX (compat check only in M1)
  std::string task_model_path;       // ONNX
  std::string robot_config_path;     // g1_29dof_hist.yaml

  int control_hz{200};
  int base_stable_cycles{20};        // BASE稳定最小周期（门禁第一层）
  int stable_hold_cycles{100};       // 达到目标姿态后稳定周期数
};

// 约束：
// 1) input_source 必须存在
// 2) backend=mujoco 时 M1 仅启用 keyboard
// 3) task模型路径可读；base模型路径在M1可选
```

---

## 4.1) MuJoCo 启动保护参数（M1 当前实现）

为降低无起身策略时的起步跌倒风险，运行时新增如下参数（Python/launch）：

- `mujoco_startup_support_mode`：默认 `m1_standby`
  - `legacy`：历史行为（启动时常规拉起 walking 相关路径）
  - `m1_standby`：优先 `standby_controller` 启动，避免启动阶段立即配置 task controller
- `mujoco_spawn_inactive_controllers`：默认 `false`
  - `false`：不在启动阶段预加载其它 inactive controller
  - `true`：保留历史预加载行为

设计目的：
- M1 先保证 `PASSIVE -> BASE_ACTIVE(standby/base)` 路径稳定。
- task controller 仅在后续切换阶段参与，不阻塞安全启动。
- 防回退锁：当 `m1_standby` 与 `spawn_inactive_controllers=true` 同时出现时，
  runtime 会强制改写为 `spawn_inactive_controllers=false` 并打印告警。

---

## 5) InputAdapter 接口

```cpp
class IInputAdapter {
 public:
  virtual ~IInputAdapter() = default;
  virtual void start() = 0;
  virtual void stop() = 0;
  virtual std::optional<RuntimeEvent> poll_event() = 0; // 边沿触发
};
```

M1 键盘映射建议（对齐 ASAP 习惯，保留最小子集）：

- `[` -> `SWITCH_TO_BASE`（在 `PASSIVE` 下等价进入 `BASE_ACTIVE`；在 `TASK_ACTIVE` 下进入 N 周期减速窗口后回 base）
TASK->BASE 当前安全参数（M1）：
- `task_to_base_blend_cycles`：默认 `80`
- `task_to_base_speed_gate_mps`：默认 `0.35`（基于 `/tf` 的基座速度门禁）
- `task_to_base_switch_max_wait_cycles`：默认 `300`
- `task_to_base_estop_min_z`：默认 `0.20`（减速窗口内近跌倒触发 E_STOP）

说明：
- 减速窗口没有被撤回；之前出现回切倒地的关键原因是窗口过短（`10` cycles）且未包含速度门禁。
- 当前实现会在窗口内等待更稳态的切换时机，并提供近跌倒急停兜底。

- `]` -> `ACTIVATE_TASK`
- `;` -> `SWITCH_TO_BASE`（兼容旧按键）
- `o` -> `E_STOP`
- `i` -> `RESET_TO_PASSIVE`

---

## 6) BackendAdapter 接口

```cpp
struct Observation {
  std::vector<float> state;
  bool valid{false};
};

struct Action {
  std::vector<float> motor_cmd;
};

struct RobotStatus {
  bool comms_ok{false};
  bool estimator_ok{false};
  bool joint_limits_ok{false};
};

class IBackendAdapter {
 public:
  virtual ~IBackendAdapter() = default;
  virtual bool init(const RuntimeConfig& cfg) = 0;
  virtual Observation read_observation() = 0;
  virtual RobotStatus get_robot_status() = 0;
  virtual bool write_action(const Action& action) = 0;
  virtual bool set_control_mode(RuntimeState state) = 0;
};
```

M1：先实现 `MujocoBackendAdapter`，`UnitreeBackendAdapter` 可保留空实现与接口对齐。

---

## 7) PolicyAdapter 接口（Recovery / Task）

```cpp
struct PolicyOutput {
  Action action;
  bool is_stable{false};
  bool target_posture_reached{false};      // recovery policy关键输出
  bool is_ready_for_task_switch{false};
};

class IPolicyAdapter {
 public:
  virtual ~IPolicyAdapter() = default;
  virtual bool init(const std::string& model_path) = 0;
  virtual PolicyOutput step(const Observation& obs) = 0;
  virtual void reset() = 0;
};
```

- `RecoveryBasePolicyAdapter`：在M1中可作为可选兼容层，BASE控制语义由 `standby_controller` 承担
- `TaskPolicyAdapter`：输出 action，可将稳定字段置默认

---

## 8) SafetySupervisor 接口

```cpp
class SafetySupervisor {
 public:
  GuardStatus evaluate(const Observation& obs,
                       const RobotStatus& status,
                       const PolicyOutput& base_out) const;

  bool should_force_estop(const Observation& obs,
                          const RobotStatus& status) const;
};
```

任务切换门禁：

- `guard.ready_for_task_switch() == true`
- 且连续满足 `stable_hold_cycles`

---

## 9) StateMachine 接口

```cpp
class StateMachine {
 public:
  RuntimeState current() const;
  bool transit(RuntimeEvent ev, const GuardStatus& guard); // 成功返回true
};
```

M1 合法迁移：

- `PASSIVE + ACTIVATE_BASE -> BASE_ACTIVE`
- `BASE_ACTIVE + ACTIVATE_TASK -> TASK_ACTIVE`（guard通过）
- `TASK_ACTIVE + SWITCH_TO_BASE -> BASE_ACTIVE`
- `* + E_STOP -> E_STOP`
- `E_STOP + RESET_TO_PASSIVE -> PASSIVE`

---

## 10) PolicyManager 接口

```cpp
class PolicyManager {
 public:
  bool init(const RuntimeConfig& cfg);
  void reset_all();

  PolicyOutput step_base(const Observation& obs);
  PolicyOutput step_task(const Observation& obs);
};
```

---

## 11) Runtime 主循环（伪代码）

```cpp
while (running) {
  auto maybe_ev = input->poll_event();
  if (maybe_ev.has_value()) {
    pending_event = maybe_ev.value();
  }

  Observation obs = backend->read_observation();
  RobotStatus status = backend->get_robot_status();

  PolicyOutput base_out{};
  Action action_zero = zero_action();
  Action action_cmd = action_zero;

  switch (sm.current()) {
    case RuntimeState::PASSIVE:
      action_cmd = action_zero;
      break;

    case RuntimeState::BASE_ACTIVE:
      base_out = pm.step_base(obs);
      action_cmd = base_out.action;
      break;

    case RuntimeState::TASK_ACTIVE:
      action_cmd = pm.step_task(obs).action;
      break;

    case RuntimeState::E_STOP:
      action_cmd = action_zero;
      break;
  }

  GuardStatus guard = safety.evaluate(obs, status, base_out);

  if (safety.should_force_estop(obs, status)) {
    sm.transit(RuntimeEvent::E_STOP, guard);
  } else if (pending_event.has_value()) {
    sm.transit(pending_event.value(), guard);
    pending_event.reset();
  }

  backend->set_control_mode(sm.current());
  backend->write_action(action_cmd);
  logger.log_tick(sm.current(), guard, status);
  sleep_until_next_cycle();
}
```

---

## 12) M1 最小测试钩子（建议）

需要至少提供以下断言接口：

- `runtime_state` 查询
- `last_reject_reason`（切换被拒绝时）
- `last_reject_code`（结构化拒绝码，便于自动验收）
- `stable_hold_counter`

最小用例：

1. 启动后状态为 `PASSIVE`
2. 触发 `ACTIVATE_TASK`（未站稳）被拒绝
3. 触发 `ACTIVATE_BASE`（对应 `standby_controller` 路径），达到 standing 后允许切到 `TASK_ACTIVE`
4. `SWITCH_TO_BASE` 可回切
5. `E_STOP` 在任意态可抢占

建议拒绝码（当前实现）：

- `guard_not_ready`
- `task_controller_not_ready`
- `controller_switch_failed`
- `illegal_transition`

默认执行入口（测试规则）：

```bash
ros2 launch motion_tracking_controller runtime_m1.launch.py \
  profile_json:=/abs/path/runtime_m1_profile.json
```

说明：
- M1 测试默认走 `ros2 launch`，保证与实际运行形态一致。
- 模型来源统一以 `profile_json` 为准（base/task 的 model_path 或 wandb_path 均在 profile 内维护）。
- `python3 scripts/runtime_m1.py ...` 仅用于排障，不作为默认验收入口。

推荐启动参数（当前）：

```bash
ros2 launch motion_tracking_controller runtime_m1.launch.py \
  input_source:=keyboard \
  base_model_path:=/root/colcon_ws/src/motion_tracking_controller/models/base/model_6600.onnx \
  task_model_path:=/root/colcon_ws/src/motion_tracking_controller/models/base/model_6600.onnx \
  auto_start_mujoco:=true \
  mujoco_startup_support_mode:=m1_standby \
  mujoco_spawn_inactive_controllers:=false \
  auto_arm_task_on_activate:=false
```

注意：
- 上述 `task_model_path` 仅用于联调占位。
- 若要真正进入 task controller，需提供符合 `walking_controller` 元数据要求的 task ONNX（例如包含 `joint_names`）。

---

## 13) 兼容你的当前约束（已对齐）

- 分支：`whole_body_tracking@autoresearch` + `motion_tracking_controller@autoresearch`
- 机器人：`G1 29DoF`
- base policy（M1语义）：`standby_controller`（recovery 控制器）
- 输入实现优先级：`keyboard > xbox > unitree_remote`
- 运行时：`--input_source` 指定唯一输入源
- M1：sim2sim + keyboard first

---

## 14) TODO：上肢跨策略插值 + 自动回闭环（参考 ASAP）

目标（待实现）：
- 在 `BASE_ACTIVE(standby)` -> `TASK_ACTIVE` 过渡时，对上肢关节执行 3 秒实时插值，避免直接切换带来的上肢突变。
- 在 task 结束后，执行反向插值回 base/standby 姿态，并自动切回 `BASE_ACTIVE`，闭环当前运控流程。

实现要点：
- 关节对齐：
  - 不能假设 standby 与 task 的上肢关节索引一致；
  - 必须按 joint-name 建立映射（`standby_joint_name -> task_joint_name`），支持左右臂及躯干上肢关节。
- 插值输入：
  - 起点：standby 标准动作当前上肢关节角；
  - 终点：task 参考轨迹初始帧上肢关节角（或任务结束时目标回姿）。
- 插值执行：
  - 固定窗口：`3.0s`；
  - 每控制周期实时更新插值系数 `alpha in [0, 1]`；
  - 插值期间保持下肢稳定优先，不改变 M1 的站立安全门禁。
- 终端可观测性：
  - 打印文本进度条（如 `[####......] 40%`）；
  - 标记当前阶段：`base->task arm blend` / `task->base arm blend`。
- 闭环逻辑：
  - task 完成事件触发后自动进入 `task->base` 插值阶段；
  - 插值完成后自动执行 controller switch 到 `standby_controller`。

建议新增参数（草案）：
- `upper_body_blend_duration_s`（默认 `3.0`）
- `upper_body_blend_enable`（默认 `true`）
- `upper_body_joint_map_json`（可选，显式 joint-name 映射）

---

## 15) 新增：Trace 诊断接口（已实现，供 M1 排障）

为解决“切换成功但物理接管失败”的定位问题，runtime 新增证据链采集能力。

### 15.1 参数接口

- `trace_enable`：是否开启 trace（默认 `false`）
- `trace_output_jsonl`：输出文件路径（空则自动写到 `/tmp/runtime_m1_trace_*.jsonl`）
- `trace_stride`：tick 采样步长（默认 `1`）
- `trace_joint_names_csv`：关节观测白名单（逗号分隔；空则用上肢插值关节集）

### 15.2 采集内容

- `session_start/session_end`
- `event`（keyboard/script）
- `transition`（before/after + switch 结果）
- `reject`（code/reason）
- `phase_start/phase_end`（base->task blend、task->base decel）
- `tick` 快照：
  - state、stable_hold、task_gate、decel 计数
  - pelvis `z` 与速度（来自 `/tf`）
  - `joint_pos`（来自 `/joint_states`）
  - 最近一次 blend 命令（`alpha + joint_pose`）
  - base/task policy 的 step 计数与输入/输出摘要

### 15.3 自测入口（已接入）

- `SELFTEST_MODE=trace_diag bash scripts/selftest_m1.sh`
- 事件脚本：`scripts/m1_trace_diag_events.json`
- 专项脚本：`scripts/selftest_m1_trace_diag.sh`

### 15.4 当前已知诊断结论（需要后续 Agent 关注）

- 现有 200-tick post-switch 窗口可判断“短时接管是否稳定”；
- 仍需扩展到 500~800 tick 检测晚发低高度事件；
- `base_to_task_max_delta=0` 说明上肢目标配置与 standby 几乎一致，需提供可见差值配置以验证插值效果。

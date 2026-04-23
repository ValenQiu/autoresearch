# M3.P2 · Sim2Real 语义对齐矩阵（Gate A 冻结文档）

**范围**：UHC `sim2real_redo` 分支；Unitree G1 29DoF；`unitree_hg` IDL；CycloneDDS。
**状态**：🚧 骨架（v0，2026-04-23）——填确定项；TBD 项由 P2.2-P2.4 证据补齐。
**验收**：Gate A = 本矩阵所有 `status` 列 = `FROZEN`，人工 review 签字，无 TBD。

## 0. 如何读这张矩阵

- 一行 = 一个**跨边界契约**（sim / mock / real 必须对齐的一条语义）
- 列约定：
  - `contract` 契约名（stable ID，不改）
  - `sim (MujocoBackend)` UHC sim2sim 当前实现值 / 字段位置
  - `mock (UnitreeBackend via unitree_mujoco)` 官方 bridge 通过 DDS 暴露给 UHC 的值
  - `real (UnitreeBackend via 真机 SDK)` 真机 DDS 暴露的值
  - `source of truth` 冲突时以谁为准
  - `verify by` 验证脚本或代码路径
  - `status` `FROZEN` / `TBD / evidence` / `RESOLVED_BY_PHASE_X`
- 违反矩阵的实现 PR 拒绝，必须先改矩阵。

## 1. 通信层（DDS / topic / IDL）

| # | contract | sim (MujocoBackend) | mock (unitree_mujoco bridge) | real (真机 SDK) | source of truth | verify by | status |
|---|---|---|---|---|---|---|---|
| C.1.1 | DDS IDL | n/a | `unitree_hg` | `unitree_hg` | 真机 | `selftest_real.py::test_idl_type` | FROZEN |
| C.1.2 | 下发 topic | n/a | `rt/lowcmd` | `rt/lowcmd` | 官方 | `scripts/check_real_env.py` | FROZEN |
| C.1.3 | 回读 topic | n/a | `rt/lowstate` | `rt/lowstate` | 官方 | `scripts/check_real_env.py` | FROZEN |
| C.1.4 | DDS domain | n/a | `1` (lo) | `0` (enp2s0) | 社区约定（ASAP/RoboJuDo/官方） | `profile.backend.domain_id` | FROZEN |
| C.1.5 | 网卡 interface | n/a | `lo` | `enp2s0` / 现场 | 用户现场 | `profile.backend.interface` | FROZEN |
| C.1.6 | state publish rate | n/a | ≥500 Hz（官方 bridge 默认 `SIMULATE_DT=0.005` = 200 Hz；需确认） | 500 Hz（真机） | 真机 | Observability 实测 | TBD / evidence 需要跑官方 bridge 确认 |
| C.1.7 | cmd rate | ≤50 Hz（UHC `PolicyRunner` 主循环） | 50 Hz | 50 Hz | UHC / 策略训练配置 | Observability 实测 | FROZEN |

## 2. 命令语义（RobotCmd → LowCmd.motor_cmd[i]）

| # | contract | sim (MujocoBackend) | mock / real (LowCmd) | source of truth | verify by | status |
|---|---|---|---|---|---|---|
| C.2.1 | `q_target` 单位 | rad | rad (`motor_cmd[i].q`) | URDF/训练 | contract 单元测 | FROZEN |
| C.2.2 | `dq_target` 单位 | rad/s（当前未用） | rad/s (`motor_cmd[i].dq`) | 官方 | contract 单元测 | FROZEN |
| C.2.3 | `kp` / `kd` 单位 | N·m/rad / N·m/(rad/s) | 同左 | UHC / BeyondMimic 约定（看 `config/policies/*.yaml` kp 数量级） | contract 单元测 | FROZEN |
| C.2.4 | `tau_ff` 单位 | N·m（当前未用） | N·m (`motor_cmd[i].tau`) | 官方 | contract 单元测 | FROZEN |
| C.2.5 | 关节序（RobotCmd 里的 i=0..28） | URDF canonical | URDF canonical | UHC `robot_cfg.joint_names` | `selftest.py::test_joint_order` | FROZEN |
| C.2.6 | motor 序（LowCmd 里 i=0..28） | n/a | Unitree G1 official motor index | 真机 | `g1_29dof_real.yaml:motor_mapping` | TBD / evidence 从官方 `unitree_robots/g1/g1_joint_index_dds.md` 抄 |
| C.2.7 | `motor2joint=-1` 语义 | n/a | 该槽位不用，回退默认 q | UHC 约定 | `UnitreeBackend.read_state` 单元测 | FROZEN |
| C.2.8 | `mode_pr` | n/a | 0 (PR) / 1 (AB) | 官方 | `LowCmd.mode_pr` | TBD / 需确认 UHC 用哪个模式 |
| C.2.9 | `level_flag` | n/a | `0xAA`（low-level） | 官方 | `LowCmd.level_flag` | FROZEN |
| C.2.10 | `effort_limit` 执行边界 | sim: MuJoCo XML `ctrlrange` 软 clip 后 | real: 电机控制器硬限；`LowCmd.tau` 被电机侧拒绝 | 真机 | `safety_guard.warn_joint_limits` 扩展 | FROZEN |
| C.2.11 | 命令 seq（防丢 / 防重放） | 自生成 monotonic | `motor_cmd[i].reserve[?]` 或自定义？（TBD） | 官方 | Observability 对账 | TBD / evidence |

## 3. 状态语义（LowState → RobotState）

| # | contract | sim (MujocoBackend) | mock / real (LowState) | source of truth | verify by | status |
|---|---|---|---|---|---|---|
| C.3.1 | `joint_pos` 单位/顺序 | rad, URDF canonical | rad, motor→joint 反向映射回 URDF canonical | 真机 | `UnitreeBackend.read_state` 单元测 | FROZEN |
| C.3.2 | `joint_vel` | rad/s, URDF canonical | 同上 | 真机 | 同上 | FROZEN |
| C.3.3 | IMU quaternion 约定 | MuJoCo `qpos[3:7]` wxyz | `imu_state.quaternion` 字段顺序（TBD：官方 hg IDL 是否 wxyz？） | 真机 | `selftest_real.py::test_imu_quat_convention` | TBD / evidence 从 unitree_hg IDL 源文件读 |
| C.3.4 | IMU ang_vel 参考系 | body frame | `imu_state.gyroscope` body frame | 官方 | 单元测 | FROZEN |
| C.3.5 | IMU lin_acc 参考系 | sim 没有（可从 qvel 差分） | `imu_state.accelerometer` body frame（含重力） | 官方 | 单元测 | FROZEN |
| C.3.6 | `tick` 来源 | 自生成 monotonic uint64 | `LowState.tick` | 真机 | freshness 测试 | FROZEN |
| C.3.7 | freshness 判定 | 不适用 | `tick_new > tick_last` | UHC 约定 + `unitree-g1-sdk-dds-mock` skill | `selftest_real.py::test_stale_frame_not_accepted` | FROZEN |
| C.3.8 | `state_timeout_ms` | 不适用 | 100 ms（保守，现场可调） | UHC default | Observability 统计 | FROZEN |
| C.3.9 | `base_pos` / `base_lin_vel` | sim: MuJoCo qpos/qvel | real: **不存在** | — | `RobotState.base_pos is None` on real | FROZEN |
| C.3.10 | `body_xpos/xquat/xmat` | sim: `MujocoBackend.get_body_frame(name)` 扩展 API | real / mock: **不提供**（BeyondMimic 真机走 FK） | — | BeyondMimic 分路测 | FROZEN |

## 4. 安全语义

| # | contract | sim / mock / real | source of truth | verify by | status |
|---|---|---|---|---|---|
| C.4.1 | 自动 E_STOP 开关 | `height_estop_enabled=false`（全 profile 默认） | 项目级约束：**仅手动按键 `o`** | `DEVELOPMENT_RULES.md` | safety_guard 代码审查 | FROZEN |
| C.4.2 | tilt 告警阈值 | 不告警 | `tilt_warn_rad: 0.5` | UHC default | `SafetyGuard.check_tilt` | FROZEN |
| C.4.3 | freshness warn 阈值 | 不适用 | 50 ms | UHC default | Observability 日志 | FROZEN |
| C.4.4 | torque envelope warn | 不告警 | `effort_limit × 0.85` | UHC default | `SafetyGuard.warn_torque_envelope` | FROZEN |
| C.4.5 | E_STOP 状态下 kp/kd | `kp=50, kd=5`（damping） | 同（或 `kp=0, kd=<real_default>` ? TBD） | UHC policy_runner 现有 | `selftest.py` 回归 | TBD / evidence 真机 damping 最佳实践 |

## 5. 时序 / 频率

| # | contract | sim | mock / real | source of truth | verify by | status |
|---|---|---|---|---|---|---|
| C.5.1 | 控制循环频率 | 50 Hz | 50 Hz | 策略训练约定 | `PolicyRunner.run()` | FROZEN |
| C.5.2 | physics step | 200 Hz (`sim_dt=0.005`) | 200 Hz（官方 bridge 默认 `SIMULATE_DT=0.005`） | 官方 | `MujocoBackend.sim_dt` | FROZEN |
| C.5.3 | state publish rate | — | **TBD**（官方 bridge 是否每 `sim_dt` 发一次？） | 官方 | Observability 实测 | TBD |
| C.5.4 | cmd 消费策略 | 同步 write_cmd 立即 step | 最新帧（drop 旧帧）/ 排队？ | 官方 bridge 行为 | 代码审查 + 实测 | TBD |

## 6. BeyondMimic worldToInit（DP2 决策执行）

| # | contract | sim | mock / real | verify by | status |
|---|---|---|---|---|---|
| C.6.1 | anchor body world pose 来源 | `MujocoBackend.get_body_frame(anchor_body)` | `pelvis IMU quat + joint_pos → URDF FK` | `BeyondMimicPolicy._compute_world_to_init` 分支 | P3.3 实现后 FROZEN |
| C.6.2 | FK 实现库 | 不适用 | TBD：`pin` / `robot_descriptions` / 手搓 | FK 单元测 (FK vs MuJoCo body_frame) | TBD / P3.3 |
| C.6.3 | FK 精度门槛 | 不适用 | anchor pos 误差 < 1cm；anchor quat 角误差 < 0.05 rad | `tests/test_fk_accuracy.py` | TBD / P3.3 |

## 7. 与 ASAP / BeyondMimic / RoboJuDo 三方对照（P2.3）

| # | 维度 | ASAP（deepmimic_dec_loco_height.py） | BeyondMimic（MotionOnnxPolicy） | RoboJuDo（UnitreeEnv） | 本项目（UHC） |
|---|---|---|---|---|---|
| T.1 | 下发三元组 | `(q, kp, kd)` | `(q, kp, kd)` + yaml 静态 kp/kd | `(q, kp, kd, tau_ff)` | `(q, kp, kd)` → 渐进升到 `RobotCmd` |
| T.2 | 控制频率 | 50 Hz | 50 Hz（controller） + 500 Hz（state estimator） | 可配 | 50 Hz |
| T.3 | sim/real 切换 | `INTERFACE=eth0` | `real.launch.py` | `env_type` 字段 | `profile.backend.interface + mode` |
| T.4 | 进程模型 | 双进程（sim_env ⊥ rl_policy via DDS） | ROS2 node 图 | **单进程** | **单进程**（P3 与 RoboJuDo 对齐） |
| T.5 | 依赖 | ros-humble + robostack + unitree_sdk2_python | ROS2 Jazzy + legged_control2 | pip + 可选 unitree_sdk2py | pip + 可选 unitree_sdk2py（同 RoboJuDo） |
| T.6 | IDL | `unitree_go`（Go2） | `unitree_hg`（G1） | 双支持 | `unitree_hg`（G1） |
| T.7 | 急停 | 按键 + 自动 | 手柄 | 手柄 + 自动 | **仅手动 `o`** |

## 8. Attempt1/2 差异点（P2.4，风险输入）

（P2.4 从 `research/m3_r5_main_vs_sim2real_debug_diff_review.md` 摘录高风险项；此处保留表位，不复制实现细节。）

| # | attempt1 / 2 的做法 | 风险 | 本项目如何规避 |
|---|---|---|---|
| — | TBD（P2.4 填） | — | — |

## 9. 冻结 / 评审

- [ ] P2.2：TBD 行补齐证据（真机 SDK 字段抽样、官方 bridge 实测 `state_publish_rate`）
- [ ] P2.3：T.1-T.7 对照完整（从 ASAP / BeyondMimic / RoboJuDo 源码 review）
- [ ] P2.4：§8 风险点写完
- [ ] P2.5：人工评审签字；签字后本文件 `status` 列全部 `FROZEN`
- [ ] **Gate A**：满足上述所有 → 进入 P3（`uhc/backends/unitree_backend.py` 实现期）

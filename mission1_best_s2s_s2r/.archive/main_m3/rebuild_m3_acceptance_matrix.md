# M3-R 验收矩阵（ASAP 对齐 + 差分防灾）

## 1. 目的

本矩阵用于 M3-R（Sim2Real 推倒重来）阶段的统一验收，覆盖：

- ASAP 语义对齐（必须）
- UHC 闭环功能验收（必须）
- 新旧实现差分审查（防灾难性更新）

## 2. 对齐矩阵（ASAP -> UHC，R1 冻结版）

| 类别 | ASAP 期望语义 | UHC 冻结实现语义 | 验证方式 | 通过标准 |
|---|---|---|---|---|
| DDS topic | `rt/lowcmd` / `rt/lowstate` | `backend.cmd_topic`=`rt/lowcmd`；`backend.state_topic`=`rt/lowstate` | profile + 启动日志 | topic 完全一致 |
| Domain / Interface | 同域同网卡可发现 | `domain_id` + `communication.interface`（`lo`/`enp2s0`）双参数共同生效 | `check_real_env.py` + 启动日志 | 配置与运行一致 |
| LowCmd.q | 目标关节位置 | `write_action.q_target` 按 `motor2joint` 映射写入 | `selftest_real.py` Test2/4 | 映射正确 |
| LowCmd.dq | 目标关节速度 | `write_action` 默认 `estimate`：由相邻 `q_target` 有限差分得到并限幅 | `selftest_real.py` + 命令采样 | 非全零且无异常尖峰 |
| LowCmd.kp/kd | PD 增益 | 按 joint 直接写入并强制非负 | `selftest_real.py` Test2 | 与输入一致 |
| LowCmd.tau | 前馈力矩 | 当前冻结为 `0`（R1/R2 不启用前馈） | 命令采样 | 字段存在且可控 |
| LowState.motor | 电机状态读回 | `motor_state.q/dq` 经 `joint2motor` 回填 `joint_pos/joint_vel` | `selftest_real.py` Test2 | shape 与语义正确 |
| LowState.imu | 姿态与角速度 | 读取 `imu_state.quaternion(wxyz)` + `imu_state.gyroscope` | `selftest_real.py` Test2 | shape 正确 |
| LowState.tick/fresh | 新鲜帧判据 | 以 bridge 提供的 `last_fresh_rx_monotonic`/tick 变化判新帧，不以对象非空判新鲜 | `selftest_real.py` Test3/5 | 断流与冻帧均可超时 |
| 超时行为 | stale frame 不可消费 | 超时后 `read_state -> None`，并有节流告警 | `selftest_real.py` + 日志 | 行为稳定 |
| 映射回退 | `motor2joint=-1` | unmapped 电机回写 default angle，不发送业务目标 | `selftest_real.py` Test4 | 回退正确 |
| 控制时序（Bridge） | 可解释且稳定 | R3 固化：`publish state -> consume cmd -> step` | bridge smoke + 时序日志 | 与冻结规格一致 |

### 2.1 约束说明（冻结）

- `tau` 前馈在 R1/R2 冻结为 0，不代表长期目标；R3/R4 评估是否开放。
- `dq` 采用有限差分估计以避免“全零速度目标”导致的语义偏差。
- quat 约定统一为 `wxyz`，若下游使用 `xyzw` 必须显式转换。

## 3. 功能验收矩阵（M3.R4）

| 场景 | 命令/流程 | 指标 | 通过标准 |
|---|---|---|---|
| Bridge 冒烟 | `selftest_loopback_bridge_smoke.py` | LowState/LowCmd 连通 | PASS |
| Runner 冒烟 | `selftest_loopback_policy_runner_smoke.py` | INIT/ACTIVATE/WALK/E_STOP | PASS |
| loco 闭环 | **真机**：`sim2real_g1_loco` + `smoke_sim2real.sh` 手册项 | `min_z/max_tilt` 稳定 | 人工 + 现场日志 |
| loco 闭环（本机 Gate C 自动化） | profile `sim2real_g1_loco_loopback.yaml`（与 `sim2real_g1_loco` 同策略，robot=`g1_29dof`+`lo`）；`selftest_loopback_policy_runner_smoke.py --loco`；桥与 UHC 同 profile | 同上 smoke 阈值 | PASS（headless） |
| 超时注入 | 暂停 state 发布 | timeout/告警 | 行为符合预期 |
| 冻帧注入 | 重复旧 tick | freshness 拒收旧帧 | 行为符合预期 |

**进度（2026-04-19）**：Gate B 已由默认 Runner 冒烟覆盖；**Gate C 本机自动化** 已落地为 `--loco` + `sim2real_g1_loco_loopback.yaml`，并纳入 `selftest_mock_sim2real_chain.sh loopback`。真机 `sim2real_g1_loco` 仍以现场验收为准。

## 4. 新旧差分审查（M3.R5）

| 差分类别 | 需要输出 | 风险级别判定 |
|---|---|---|
| 字段语义差异 | LowCmd/LowState 差异表 | 缺失关键字段 = 高 |
| 时序差异 | 控制循环时序对照 | 不可解释偏差 = 高 |
| 稳定性差异 | 指标对照（tilt/min_z） | 倒地率上升 = 高 |
| 安全差异 | timeout/estop/fallback 行为对照 | 自动安全退化失效 = 高 |

审查报告（2026-04-19）：`research/m3_r5_main_vs_sim2real_debug_diff_review.md`

## 5. Gate 退出条件

- **Gate A (R1)**：对齐矩阵完整，无 TBD
- **Gate B (R3)**：两项 loopback smoke 全 PASS
- **Gate C (R4)**：loco 闭环稳定且无严重异常
- **Gate D (R5)**：差分审查完成，所有高风险项关闭

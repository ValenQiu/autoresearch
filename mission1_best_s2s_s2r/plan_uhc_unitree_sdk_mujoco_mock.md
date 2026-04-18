# 执行计划：UHC -> unitree_sdk -> mujoco（本机 DDS 闭环仿真）

## 1. 目标与边界

目标：在本机实现一条“真机协议语义”的闭环链路：

`UHC(UnitreeBackend, mock=false)` -> `unitree_sdk2py DDS` -> `Mock Robot(MuJoCo)`

边界：
- 不改变策略层与状态机语义（PolicyRunner/Policy 逻辑保持一致）；
- 仅新增 bridge 进程与必要配置；
- 保留真机最小切换路径：mock 用 `lo`，真机改为 `enp2s0`（或现场网卡）。

## 1.1 阶段目标与验收标准（强制）

| 阶段 | 目标 | 验收标准（必须满足） |
|---|---|---|
| S0 基线回归 | 确认现有 sim2sim/sim2real 基线可用 | `selftest.py` 全绿；`selftest_real.py` 全绿；`smoke_sim2real.sh preflight` 必填检查通过 |
| S1 协议对齐 | 固化 LowCmd/LowState 字段与 topic 契约 | `rt/lowcmd/rt/lowstate` 字段映射表冻结；`motor2joint=-1` fallback 与 mode 语义有测试覆盖 |
| S2 Loopback 闭环 | 跑通 `UHC -> DDS -> MuJoCo bridge -> DDS -> UHC` | 在 `interface=lo` 下可完成 init/activate/estop；断流与旧帧注入可复现且日志可观测 |
| S3 严格审查 | 对 freshness、安全与映射进行风险收口 | Codex 审查无高严重阻塞项；**风险清单与规避措施**见 [`s3_s4_loopback_risks_and_checklist.md`](s3_s4_loopback_risks_and_checklist.md) |
| S4 真机最小切换 | 保持同一结构切到实机网卡 | 仅改 `interface: lo -> enp2s0` + 现场 `domain_id` 后可启动；**现场 checklist** 同上文档 §S4 |

## 2. 工作流（按你指定）

### 阶段 A：规划（Codex MAX）
- 输入：本计划 + 现有 `UnitreeBackend`、`sim2real` profile、ASAP 参考实现。
- 输出：
  1) 架构图（进程/话题/频率/时序）；
  2) 消息映射表（LowCmd/LowState <-> MuJoCo state）；
  3) 失效场景清单（断流、延迟、旧帧重复、topic 错配）。

### 阶段 B：实现（auto 模型）
- 只执行阶段 A 已冻结的实现清单，不做架构漂移。
- 每步提交前跑：
  - `scripts/selftest_real.py`
  - `scripts/selftest.py`（回归）

### 阶段 C：严格审查（Codex）
- 重点审查：
  1) 超时 freshness 是否基于“新帧”而非缓存对象；
  2) motor 映射与 `-1` fallback；
  3) mode/level_flag/mode_machine/mode_pr 一致性；
  4) 故障注入（断流/抖动/帧冻结）是否可复现。

## 3. 实施步骤（技术细化）

1) 新增 bridge 进程（建议 `scripts/mock_unitree_mujoco_bridge.py`）
- Subscriber：`rt/lowcmd`
- Publisher：`rt/lowstate`
- 内置 MuJoCo（scene 用 `assets/g1/scene_29dof.xml`）
- 控制律：按 LowCmd 中 `q/kp/kd/tau` 驱动 MuJoCo
- 回传：`motor_state.q/dq`、IMU quat/gyro、tick

2) 配置拆分
- 统一 loopback profile：`config/profiles/sim2real_g1_loopback.yaml`（BFM-Zero + 全任务；桥与 UHC 共用）
  - `backend.type: unitree`
  - `backend.mock: false`
  - `robot.communication.interface: lo`
  - topic 与真机一致（`rt/lowstate`, `rt/lowcmd`）

3) 运行编排
- 终端 A：启动 `mock_unitree_mujoco_bridge.py`（建议 `--profile config/profiles/sim2real_g1_loopback.yaml`）
- 终端 B：`python scripts/run.py --profile config/profiles/sim2real_g1_loopback.yaml`

4) 验证矩阵
- 正常链路：init / activate / task switch / estop
- 断流：bridge 暂停发布，确认 timeout 行为
- 帧冻结：重复旧 tick，确认 freshness 判定
- topic 错配：验证明确报错与日志

5) 自测链路（新增脚本统一入口）
- 基线链路：`scripts/selftest_mock_sim2real_chain.sh baseline`
- loopback 链路：`scripts/selftest_mock_sim2real_chain.sh loopback`
- 全量链路：`scripts/selftest_mock_sim2real_chain.sh all`

## 4. 真机最小切换路径

保持相同 profile 结构，仅改：
- `communication.interface: lo` -> `enp2s0`（或现场网卡）
- 保持 `backend.type: unitree`、topic 不变
- 确认 `unitree_sdk2py` 与 G1 SDK 版本匹配

即：**开发期跑 loopback mock，实机期只换网卡与现场 DDS 环境。**

## 5. 交付物清单

- [x] `scripts/mock_unitree_mujoco_bridge.py`
- [x] `config/profiles/sim2real_g1_loopback.yaml`
- [x] `scripts/selftest_real.py` 扩展：`Test 3` 断流/None 序列超时；`Test 5` 冻结 fresh 时间戳（模拟旧 tick 不失效）；loopback 进程级冒烟见 `selftest_loopback_bridge_smoke.py`
- [x] Runbook：`mission1_best_s2s_s2r/runbook_loopback_uhc_mujoco.md`（启动顺序、冒烟、故障注入表、切真机要点）
- [x] `scripts/selftest_mock_sim2real_chain.sh`（分阶段自测编排）
- [x] `scripts/selftest_loopback_policy_runner_smoke.py`（S2：PolicyRunner 无键盘事件注入）

S2 交互级：`scripts/selftest_loopback_policy_runner_smoke.py` 在桥 + loopback profile 下自动注入 **INIT → ACTIVATE → WALK → E_STOP**（`input_source: none`）；同时纳入 `max_tilt_deg/min_z` 稳定性判据。人工仍可用 `run.py` + 键盘做完整观感验收。

> 结论更新：在固定默认弹力绳（无热键调参）与命令驱动步进下，`selftest_loopback_policy_runner_smoke.py` 与 `selftest_mock_sim2real_chain.sh loopback` 已通过，S2 的“连通 + 基本稳定性”自测链路可复现。

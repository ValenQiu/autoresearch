# SOP：从 Sim2Sim 到 Sim2Real（G1 29DoF，UHC）

**目的**：在策略与 PolicyRunner 不变的前提下，把已在仿真中验证过的 profile 迁移到真机，并明确最小改动项与验收顺序。

**适用范围**：`universal_humanoid_controller` + `config/profiles` + `config/robots/g1_29dof_real.yaml`。

---

## 1. 概念：Sim2Sim 与 Sim2Real profile 结构差异

| 维度 | Sim2Sim | Sim2Real |
|------|---------|----------|
| `robot` | 通常 `config/robots/g1_29dof.yaml`（MuJoCo 场景等） | `config/robots/g1_29dof_real.yaml`（继承 sim 版并覆盖通信、真机安全等） |
| `backend.type` | `mujoco` | `unitree` |
| `backend` 其它字段 | 可选 `scene_xml` 等 | `mock`、`state_topic`、`cmd_topic`、`state_timeout_ms`、电机 mode 等 |
| `base_policy` / `task_policies` | 与真机共用同一套策略 YAML/ONNX | **应尽量保持一致**，不随 sim→real 重训 |

**结论**：不能做到「只改 IP」；DDS 侧需要配置 **网卡接口名**（如 `enp2s0`）和 **DOMAIN_ID**，不是写机器人 IP。策略侧可做到「除底层与机器人配置外几乎不动」。

---

## 2. 前置条件

1. 已在 **Sim2Sim** 下用目标 profile 完成策略与流程验收（站立、行走、切 task、急停等按项目要求）。
2. 真机侧：支架/安全绳、急停路径、与 G1 同网段网卡已确认。
3. Python 环境：`robo_deploy`（或项目约定环境）可导入 `uhc`、`onnxruntime`；真机 DDS 需 `unitree_sdk2py`（见 `scripts/check_real_env.py`）。

---

## 3. Sim2Sim 校验（上线前必跑）

在 `universal_humanoid_controller` 目录：

```bash
conda run -n robo_deploy python scripts/selftest.py
```

针对你实际使用的交互 profile：

```bash
conda run -n robo_deploy python scripts/run.py --profile config/profiles/<你的_sim2sim>.yaml
```

记录：profile 路径、关键按键序列、异常现象。

---

## 4. 迁移步骤：从 Sim2Sim profile 生成 Sim2Real profile

1. **复制** 已验证的 `sim2sim_*.yaml` 为新的 `sim2real_*.yaml`（勿直接覆盖 sim 文件）。
2. **必改**：
   - `robot:` → `config/robots/g1_29dof_real.yaml`
   - `backend:` 整段替换为 `type: unitree`，并至少包含：
     - `mock: false`（无真机调试时可临时 `true` 仅跑通 Runner）
     - `state_topic: rt/lowstate`
     - `cmd_topic: rt/lowcmd`
     - `state_timeout_ms: 100`（可按现场调整，见下文说明）
3. **不改**（除非真机实测需要）：
   - `base_policy` 的 `config`、`model_path`、`wandb_path`
   - `task_policies` 列表及各 task 的 `config` / `wandb_path` / `motion_length_s` 等
4. **真机网络**：编辑 `config/robots/g1_29dof_real.yaml` 中 `communication.interface` 为实际网卡名；`domain_id` 与现场 DDS 一致。
5. **输入**：当前仓库若仅实现 `keyboard`，`input_source` 保持 `keyboard`；手柄需单独实现后再改。

参考真机入口：`config/profiles/sim2real_g1_loco.yaml`。

---

## 5. Sim2Real 自动化预检（不连真机也可跑）

```bash
cd /path/to/universal_humanoid_controller
conda run -n robo_deploy ./scripts/smoke_sim2real.sh preflight
```

或分步：

```bash
conda run -n robo_deploy python scripts/check_real_env.py
conda run -n robo_deploy python scripts/selftest_real.py
```

全量回归（防影响 sim2sim）：

```bash
conda run -n robo_deploy python scripts/selftest.py
```

---

## 6. 真机 Smoke（人工）

```bash
./scripts/smoke_sim2real.sh guide
conda run -n robo_deploy python scripts/run.py --profile config/profiles/<你的_sim2real>.yaml
```

按 guide 中顺序：安全准备 → `i` 初始化 → `]` 激活 loco → 速度命令 → `o` 急停；可选断网验证通信超时行为（需在理解风险前提下进行）。

---

## 7. 回滚与记录

- **回滚**：继续使用原 `sim2sim_*.yaml` + `mujoco` 后端做问题复现。
- **记录**：使用的 profile、`g1_29dof_real.yaml` 中网卡与 `domain_id`、SDK 版本、异常日志。

---

## 8. 常见问题

**Q：能否只改「IP」就上真机？**  
A：不能。需改 `backend` + `robot`（真机 YAML），网络侧改 **interface / domain**，不是机器人 IP。

**Q：`state_timeout_ms` 是什么？是否等于控制频率？**  
A：见仓库内说明或 `UnitreeBackend` 注释。它是 **多久收不到新的 LowState 就视为通信失效** 的阈值（秒级为 `state_timeout_ms/1000`），与 **50Hz 控制频率不是同一概念**；控制频率由 PolicyRunner 与 `control_rate_hz` 决定。

---

## 9. `dummy_task` 与当前 UHC DDS 闭环的对应关系

`dummy_task` 中 `motion_tracking_controller` 的设计核心是：
- 策略编排层（状态机/策略切换）与后端适配层解耦；
- sim2sim 与 sim2real 共享同一编排逻辑，仅后端 I/O 不同。

对应到当前 UHC（你要求的 DDS 消息级闭环）：

| `dummy_task` 概念 | UHC 实现落点 | 说明 |
|---|---|---|
| `MujocoBackend` / `UnitreeBackend` 适配层 | `uhc/backends/mujoco_backend.py` / `uhc/backends/unitree_backend.py` | 同构：策略层不感知后端细节 |
| 统一状态机切换 | `uhc/core/policy_runner.py` + `state_machine.py` | 保持 `PASSIVE/BASE/TASK/E_STOP` 编排 |
| 真机协议一致性 | `UnitreeBackend` 的 `rt/lowstate` / `rt/lowcmd` | 与 ASAP / Unitree SDK 低层主题保持一致 |
| sim2real 本机 mock | `UHC -> unitree_sdk2py -> bridge(MuJoCo)` | 作为“假真机”链路验证 DDS 与语义 |

结论：两套方案是**架构同构**，只是实现层级不同（ROS2 controller 语义 vs DDS 话题语义）。

---

## 10. Unitree G1 文档蒸馏（SDK 重点）

> 说明：官方站点部分页面对自动抓取不稳定（出现 CSS preload 错误）；本节基于可访问章节索引 + 现有 ASAP/SDK 使用代码进行工程化归纳。实施时请以官方页面最新字段为准。

### 10.1 SDK 重点（对 UHC 开发最关键）

1. **通信范式：DDS topic + IDL 消息**
   - 核心主题：`rt/lowcmd`（控制下发）、`rt/lowstate`（状态上报）
   - 核心类型：`LowCmd_`、`LowState_`、电机子结构（`MotorCmd_` / `motor_state`）

2. **低层控制语义（G1）**
   - 典型字段：`q/dq/kp/kd/tau`、`level_flag`、`mode_machine`、`mode_pr`
   - 常用停止常量：`PosStopF`、`VelStopF`
   - 常见模式：弱/强电机 mode 区分（ASAP 代码中 `0x01` / `0x0A`）

3. **状态侧最小闭环字段**
   - 关节：`motor_state[i].q/dq`
   - IMU：`quaternion(wxyz)`、`gyroscope`
   - 时戳/节拍：`tick`（可用于 freshness 判定）

4. **工程风险点**
   - 旧帧缓存导致 timeout 失效；
   - `joint2motor/motor2joint` 映射不一致；
   - topic/domain/interface 错配导致“有进程无数据”。

### 10.2 建议阅读顺序（官方）

- 开发总览：[G1 SDK Development Guide](https://support.unitree.com/home/en/G1_developer)
- 快速上手：[Quick Start](https://support.unitree.com/home/en/G1_developer/quick_start)
- 基础服务接口（重点）：[Basic Services Interface](https://support.unitree.com/home/en/G1_developer/basic_services_interface)
- DDS 接口章节：[DDS Services Interface](https://support.unitree.com/home/en/G1_developer/dds_services_interface)
- SDK 概览入口：[SDK Overview](https://support.unitree.com/home/en/G1_developer/sdk_overview)

---

## 11. 本机 DDS 闭环 mock 与真机最小切换

### 本机 mock（推荐）
- 运行链路：`UHC(UnitreeBackend, mock=false)` -> `unitree_sdk2py DDS` -> `MuJoCo bridge` -> `rt/lowstate`
- 网卡：`communication.interface: lo`

### 真机切换（最小改动）
- 保持同一 profile 结构与 topic；
- 仅将 `communication.interface: lo` 改为真机网卡（如 `enp2s0`）；
- 校验 `domain_id`、SDK 版本、topic 一致。

---

**文档版本**：与 `universal_humanoid_controller` 中 `UnitreeBackend`、`scripts/selftest_real.py` 行为一致时有效；若后端语义变更请同步更新本 SOP。

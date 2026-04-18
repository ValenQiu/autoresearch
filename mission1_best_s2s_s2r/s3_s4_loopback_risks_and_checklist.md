# S3 / S4：Loopback 风险清单与真机切换 Checklist

对应计划：`plan_uhc_unitree_sdk_mujoco_mock.md`。实现代码在 **`universal_humanoid_controller`** 仓库。

---

## S3：已知风险与规避措施（短表）

| 风险域 | 现象 / 根因 | 规避与验证 |
|--------|----------------|------------|
| **Freshness（tick / `last_fresh_rx_monotonic`）** | 若 LowState **tick 不前进**，`_UnitreeSdk2Bridge` 不把 `last_fresh_rx_monotonic` 当作新帧；`UnitreeBackend._read_real_state` 会在 `state_timeout_ms` 后判无效。真机若 tick 语义与 bridge 不一致，会出现「偶发无状态」。 | 自测：`scripts/selftest_real.py` Test 5（冻结 fresh）；现场：断流/停 bridge 后应在超时内 `read_state`→`None`。确认 profile 中 `state_timeout_ms` 与现场容忍一致。 |
| **LowState 缓存 + 非阻塞读** | `read_low_state()` 只返回回调缓存，**禁止**在 `read` 路径上阻塞 `Read()`，否则主循环卡死。 | 代码约束已满足；审查时勿改回阻塞读。 |
| **`motor2joint = -1` 与默认角** | 未映射电机用 `default_joint_angles` 填 `q`，与 ASAP 语义对齐。映射表错误会导致单关节「跟错目标」。 | 自测：`selftest_real.py` Test 4；改映射后必须重跑。 |
| **LowCmd 字段语义** | UHC 侧设置 `level_flag` / `mode_machine` / `mode_pr` 及 `motor_cmd.*`；bridge 按 `q,kp,kd,tau` 做 PD+τ。与真机固件若存在 mode 差异，会出现「能发令但电机不跟」。 | 对照现场 ASAP/厂商文档冻结一版「最小必填字段表」；首机上只做小范围关节抽动验证再全开。 |
| **`write_action` 中 τ 路径** | `UnitreeBackend.write_action` 对 `tau` 有固定填充策略（与 sim2sim 直接力矩路径不完全等价）。若策略强依赖前馈力矩，loopback/真机表现可能与纯 MuJoCo 有偏差。 | 策略迭代仍以 `MujocoBackend` 为基线；上 Unitree 路径前做一次「同 profile 下关节目标/τ」对照日志。 |
| **`pelvis_z` 缺失回退** | `LowState` 若无 `pelvis_z`/`pelvisHeight` 字段，会回退 `pelvis_z_default`，**高度类诊断失真**。 | 真机/bridge 应尽量提供一致字段；依赖高度的安全/恢复逻辑上机前用日志确认实际值非常数。 |
| **bridge 与 `MujocoBackend` 节拍** | bridge：`simulate_dt`×`steps_per_ctrl`≈控制周期；可选 `--command_driven` 与 `--no-command_driven`。与单进程 `MujocoBackend` 的「每控制周期同步步进」不完全同一实现，极端下动态略有差异。 | loopback 冒烟：`selftest_loopback_policy_runner_smoke.py`；策略调参仍以 sim2sim 为主、loopback 作协议门禁。 |
| **弹力绳（仅 mock bridge）** | bridge 内弹性绳辅助站立，**真机不存在**。过度依赖绳参数会导致「mock 稳、上机落差大」。 | 上机前在文档中明确「绳仅开发期」；可选逐步 `9` 关绳做对比（仅可视化场景）。 |
| **`UnitreeBackend.set_friction`** | 当前为 **no-op**（与 `MujocoBackend` 可开关摩擦不同）。依赖 `set_friction` 的任务策略在 Unitree 路径上行为可能不一致。 | 任务策略上真机前核对；若需要，应在 Unitree 侧实现等价或文档标明不支持。 |
| **DDS 环境** | 多进程、同 `domain_id` 残留进程可导致 participant/发现异常。 | 异常时 `pkill -f mock_unitree_mujoco_bridge` 等清理；现场固定 `domain_id` 与网卡文档化。 |

---

## S4：真机最小切换演练 Checklist

**配置变更（相对 loopback profile）**

- [ ] `robot.communication.interface`：`lo` → 现场网卡（如 `enp2s0`）
- [ ] `robot.communication.domain_id`：与现场 DDS / 网段一致
- [ ] `backend.state_topic` / `cmd_topic`：与真机一致（默认 `rt/lowstate`、`rt/lowcmd`）
- [ ] `unitree_sdk2py` 与 G1 SDK 版本与现场一致（团队约定）

**现场启动顺序**

1. [ ] 确认无残留 bridge / 旧 UHC 进程占用同一 `domain_id`
2. [ ] 真机侧低层服务 / 安全链就绪（按现场规范）
3. [ ] 启动 UHC：`python scripts/run.py --profile <sim2real profile>`
4. [ ] 首帧：在 `state_timeout_ms` 内应能稳定 `read_state` 非空（或日志明确无发现）

**观测与故障定位**

- [ ] **DDS 发现**：无 LowState 时优先查网卡、防火墙、`domain_id`、是否与其它进程冲突
- [ ] **Topic**：与 `profile` 完全一致（大小写、前缀）
- [ ] **首帧 LowState**：关节维度、`quat` 合理范围
- [ ] **Timeout**：断链路（或停对端）后，应在约 `state_timeout_ms` 后表现为无有效状态/策略侧可感知，而非无限阻塞

**回退**

- [ ] 问题未定位前：切回 `lo` + mock bridge 复现，区分「协议/软件」与「现场网络/硬件」

---

## 自测矩阵（防回归，建议节奏）

| 命令 | 作用 |
|------|------|
| `scripts/selftest_mock_sim2real_chain.sh baseline` | S0：环境 + `selftest_real` + `selftest.py` |
| `scripts/selftest_mock_sim2real_chain.sh loopback` | S2：bridge 连通 + PolicyRunner loopback 稳定性 |
| `python scripts/selftest.py` | 全量策略/状态机回归 |
| `python scripts/selftest_real.py` | DDS 契约与 fake 注入 |

**CI（可选）**：在具备 `unitree_sdk2py` + MuJoCo 的 agent 上增加 `loopback` job；失败日志需保留 bridge/UHC 两行摘要。

---

## 可选：人机观感验收

- 双终端：`mock_unitree_mujoco_bridge.py` + `run.py`，键盘走 **init → activate → walk → estop**
- 与 `selftest_loopback_policy_runner_smoke.py` 结论对照，确认无「仅 GUI 才成立」的差异

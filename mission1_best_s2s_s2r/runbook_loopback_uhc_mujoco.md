# Runbook：UHC ↔ DDS ↔ MuJoCo loopback（本机 mock）

对应计划：`plan_uhc_unitree_sdk_mujoco_mock.md`。代码与脚本在 **`universal_humanoid_controller`** 仓库根目录执行。

## 前置

- 已按项目说明安装 `unitree_sdk2py`（推荐 `git clone` + `pip install -e .`），并 pin `cyclonedds==0.10.2`（与团队约定一致）。
- 本机 loopback 使用 `interface: lo`；UHC 会对 `lo` 应用 Cyclone 单播/Peer 补丁（见 `uhc/utils/cyclonedds_loopback.py`）。

## 启动顺序

1. **终端 A — MuJoCo 桥**（先起，保证有 `rt/lowstate` 发布）：

   ```bash
   cd /path/to/universal_humanoid_controller
   python scripts/mock_unitree_mujoco_bridge.py --vis --profile config/profiles/sim2real_g1_loopback.yaml
   ```

   无窗口环境可去掉 `--vis`。
   当前桥不提供弹力绳热键，默认使用固定参数（长度/刚度/阻尼）以保证复现实验一致性。

   期望：进程常驻；日志可见 DDS/MuJoCo 初始化成功；无反复阻塞。

2. **终端 B — UHC**：

   ```bash
   cd /path/to/universal_humanoid_controller
   python scripts/run.py --profile config/profiles/sim2real_g1_loopback.yaml
   ```

   期望：`UnitreeBackend` 报告 DDS 已启动；能周期性读到状态（非无限挂起）。

## 自动化冒烟（不启 GUI）

**仅 DDS + UnitreeBackend（无 PolicyRunner）：**

```bash
cd /path/to/universal_humanoid_controller
python scripts/selftest_loopback_bridge_smoke.py
```

期望输出含 `[PASS]`，且状态维度如 `joint_pos shape (29,)`。

**S2：PolicyRunner 状态机（无键盘，`input_source=none` 由脚本注入）：** `i` → `]` → `o` 等价事件序列（INIT → ACTIVATE_TASK → E_STOP）。

```bash
python scripts/selftest_loopback_policy_runner_smoke.py
```

期望输出含 `[PASS]`，且最终状态机为 `E_STOP`。

**Gate C（M3.R4，ASAP Loco 与 `sim2real_g1_loco` 同拓扑）**：桥与 UHC 均使用 `config/profiles/sim2real_g1_loco_loopback.yaml`，再跑 headless：

```bash
python scripts/mock_unitree_mujoco_bridge.py --profile config/profiles/sim2real_g1_loco_loopback.yaml
# 另开终端：
python scripts/selftest_loopback_policy_runner_smoke.py --loco
```

## 编排脚本

```bash
./scripts/selftest_mock_sim2real_chain.sh baseline   # 基线
./scripts/selftest_mock_sim2real_chain.sh loopback   # loopback 冒烟
./scripts/selftest_mock_sim2real_chain.sh all
```

## 故障注入与期望行为

| 场景 | 操作 | 期望 |
|------|------|------|
| 断流 | 停掉 bridge 或断网卡 | `read_state` 在 `state_timeout_ms` 后变为 `None`；不应永久阻塞在 `Read()` |
| 帧冻结（旧 tick） | 桥侧不再推进 tick / fresh 时间 | 与真机一致：`last_fresh_rx_monotonic` 不前进则视为过期；`scripts/selftest_real.py` 中 Test 5 覆盖该语义 |
| Topic 错配 | profile 中 state/cmd topic 与 bridge 不一致 | 无有效状态或发现失败；日志中应能区分「无数据」与配置错误 |

## 真机最小切换

将 profile 中 `robot.communication.interface` 从 `lo` 改为现场网卡（如 `enp2s0`），并确认 `domain_id` 与现场 DDS 一致；topic 名称保持不变。

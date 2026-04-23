# 严格审查：UHC `unitree_sdk -> mujoco(mock)` vs motion_tracking_controller 实现

## 结论（先给结论）

**两者不完全一致，且当前属于不同架构层级的“可跑链路”：**

- UHC 当前链路是 **Python `unitree_sdk2py` 直连 DDS topic（`rt/lowcmd`/`rt/lowstate`）+ 自建 MuJoCo bridge**；
- motion_tracking_controller（MTC）主实现是 **ROS2 controller_manager + unitree_systems 硬件抽象**，通过控制器/系统插件走真机或 MuJoCo launch，不是同一层级的 `unitree_sdk2py` 直连模型。

因此，若判断“是否一致”=“架构与接口严格同构”，答案是 **否**；若判断“是否都覆盖 Unitree 语义并可支撑 sim2real 迁移”，答案是 **部分一致**。

---

## 主要发现（按严重度）

### P0（高）：接入层不同，不可直接按“同一实现”验收

- UHC：`UnitreeBackend` 直接配置 `domain_id/interface/topic`，并在 `write_action` 写 LowCmd 字段。
- MTC：`real.launch.py` 走 `ros2_control_node` + controller spawner + `network_interface`，由系统插件承接底层通信。

**影响**：
同一策略在两边“能跑”并不代表字段/时序逐项等价；MTC 的控制器切换与启动支持（standby_controller/walking_controller）在 UHC 中并不存在。

### P1（中高）：状态机/启动策略不同

- UHC：`PolicyRunner` 管理 PASSIVE/BASE/TASK/RECOVERING/E_STOP，loopback 通过 bridge 的弹力绳与 `INIT` 过渡。
- MTC：runtime_m1 强依赖 controller_switch、base/task controller 状态与 guard（包括 TF 新鲜度、z 门限）。

**影响**：
对“稳定性已验证”的定义不同；跨仓结论不能直接复用，需要各自 gate。

### P1（中高）：观测与新鲜度 gate 机制不同

- UHC：freshness 核心在 `tick` 与 `last_fresh_rx_monotonic`。
- MTC：runtime_m1 更多依赖 `/tf`、controller state、guard 条件；并未采用同一 `tick` 判定路径。

**影响**：
断流/旧帧问题在两套实现中的报错面与观测面不同，排障脚本不能通用。

### P2（中）：节拍模型不完全同构

- UHC bridge：支持 `--command_driven`、`steps_per_ctrl` 与弹力绳 mock 机制。
- MTC：由 ROS2 控制链调度，启动支持模式由 launch 参数驱动（`startup_support_mode` 等）。

**影响**：
高动态策略的细节表现可能有偏差，尤其在切换/恢复窗口。

---

## 已对齐项（可复用）

- Unitree topic 语义（`rt/lowcmd` / `rt/lowstate`）在 UHC loopback 路径里已固定。
- 低层命令关键字段（`q/kp/kd/tau`、`level_flag/mode_machine/mode_pr`）在 UHC 侧有显式设置。
- `motor2joint=-1` fallback、freshness 超时、loopback 冒烟链路已具备可自动化验证。

---

## 评审建议（用于后续推进）

1. 把“与 MTC 一致”改写为“**语义对齐目标清单**”，不要用“实现一致”作为验收标准。
2. 真机前增加一项跨仓对照：
   - UHC 输出 LowCmd 字段快照（关键关节）
   - MTC 对应 controller 命令快照（同窗口）
   用于验证动作语义而非代码结构。
3. 保持 UHC 当前 loopback 门禁（`selftest_mock_sim2real_chain.sh loopback`）独立作为进入真机前的必跑项。


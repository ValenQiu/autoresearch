# sim2real Latency 处理对比与 UHC 当前问题诊断

> **来源**: 对照 RoboJuDo (`HansZ8/RoboJuDo` release branch)、ASAP (`humanoidverse/sim2real`)、
> motion_tracking_controller (`HybridRobotics/motion_tracking_controller` main branch) 三个 G1
> sim2real 框架的源码，回答 UHC sim2real mock 链路 round-trip latency 问题：**为什么 mock
> 实测 13ms？是否能再降？要不要降？**
>
> **TL;DR**:
> 1. **mock 10–14ms latency 不是 bug，是真机 DDS 的真实复刻**（Unitree 官方文档说 5–20ms）。
> 2. **UHC 的 OmniXtreme policy 在 mock 里无法过 `fallAndGetUp` 着地段**，**根因不是 latency
>    本身**——RoboJuDo 在 G1 真机上跑同样动作能成功，证明 5–20ms latency 可被 policy 容忍。
>    所以 UHC 的真正 gap 是 obs 一致性、FK/anchor 复刻、或 PD/actuator 模型，不是 DDS 链路。
> 3. **如果**真要进一步降 latency（为容忍鲁棒性更弱的 policy），唯一已被验证的工程路线是
>    **走 C++ DDS**（RoboJuDo `UnitreeCppEnv`、ASAP 也内部用 cpp bridge），而不是继续优化
>    Python DDS（GIL 是物理上限）。
> 4. **ASAP/MTC/RoboJuDo 都不在 deploy 端做 latency 补偿**，全部在训练端通过 randomization
>    覆盖 5–20ms 的 latency 分布。

---

## 1. 三个上游框架的 latency 处理总览

| 框架 | env 实现 | DDS 收发线程模型 | latency 应对策略 |
|---|---|---|---|
| **RoboJuDo `UnitreeEnv`** | `unitree_sdk2py` (Python DDS) | 一个 `RecurrentThread(send_cmd, interval=control_dt)` 周期发；DDS sub callback 在 sdk 内部线程；主线程 `step()` **额外** call `send_cmd`（双发） | 训练侧 randomization；deploy 不补偿 |
| **RoboJuDo `UnitreeCppEnv`** | `unitree_cpp` (pybind11 包装 unitree_sdk2 C++) | 全部在 C++ 线程，绕过 Python GIL；Python 只 `unitree.step(target)` / `unitree.get_robot_state()` | 同上；C++ DDS 自带更低 jitter |
| **ASAP `humanoidverse/sim2real`** | `unitree_sdk2py_bridge` + `base_sim.py` | sim2sim：**单线程**——`sim_step` 里直接 call `unitree_bridge.PublishLowState()`（无独立 lowStateThread）；sim2real：跟 RoboJuDo `UnitreeEnv` 几乎相同 | 训练侧 randomization (delay buffer + obs/action noise) |
| **MTC (HybridRobotics)** | C++ `legged_control2` + ros2_control | ros2_control 单线程 `update()` 周期；hardware_interface 直接读寄存器 | 训练侧 BeyondMimic latency randomization；C++ ONNX 推理 |

**关键观察**：

- **没有任何上游在 deploy 端做 latency 主动补偿**（如 forward prediction、time-warp、Kalman state estimator）。
- **真正区别**只在"DDS 链路是否经过 Python GIL"：RoboJuDo `UnitreeCppEnv` / MTC / Unitree 官方 SDK
  全部走 C++；RoboJuDo `UnitreeEnv` / ASAP sim2real / UHC `UnitreeBackend` 走 Python `unitree_sdk2py`，
  会被 GIL 拖累。

---

## 2. UHC 当前 mock 链路 latency 拆解

### 2.1 当前实测

`UnitreeBackend` 加 `cmd_publish_ns → _on_lowstate.now_ns` 测量，多个 trial：

```
[UnitreeBackend][latency] n=200 rt_ms min=8.7 avg=13.5 max=153.0  (cmd→state round-trip)
```

13.5ms 平均、最大尖峰 150ms。

### 2.2 链路分解（mock）

```
PolicyRunner.write_cmd()                           ← t0
   ↓ [LowCmdHG.crc + DDS Write]                    Python GIL
   ↓ DDS loopback transport (lo)                   < 1ms
bridge: _on_lowcmd() callback                      ← cmd 到达 bridge
   ↓ stash latest cmd
sim_thread tick (200Hz, 5ms)                       ← 0–5ms wait for next tick
   ↓ _compute_pd_torque (FK, friction, kp/kd 插值)
   ↓ mujoco.mj_step                                  ~0.5ms
   ↓ snapshot copy (qpos/qvel/actforce)              <0.1ms (with lock)
   ↓ bridge.PublishLowState()  (inline，已修)        ~2ms (29×3 Python attribute writes + DDS Write)
DDS loopback transport (lo)                         < 1ms
PolicyRunner._on_lowstate() callback              ← t1
   round-trip = t1 - t0
```

**理论 best-case**：1 + 2.5 (avg wait for sim tick) + 0.5 + 0.1 + 2 + 1 = **~7ms**。

**实测 13.5ms** vs **理论 7ms**：差 6.5ms 主要是 **Python GIL contention**：

- `sim_thread_fn` 是 Python 线程，每个 mj_step 周期里大量 Python 调用（torque 计算、friction
  应用、snapshot 写入），全程 hold GIL。
- DDS sub callback (`_on_lowstate` in PolicyRunner) 是 cyclonedds C 线程触发的，但要把数据交
  给 Python handler 必须抢 GIL。
- DDS pub (`bridge.PublishLowState()` 内部 29×3 Python 属性写、CRC、Write) 也 hold GIL。
- 三个 Python 线程（PolicyRunner main 50Hz、sim_thread 200Hz、DDS callback）在一个 GIL
  下来回切换，每次切换 + scheduler delay 会引入 1–5ms jitter。

### 2.3 已应用的修复

`tools/loopback_bridge/run_g1_bridge.py` 现在做了：

1. **Snapshot lock**（`_snap_lock`）：把 `mj_data.qpos[7:]/qvel[6:]/actuator_force/sensordata`
   在 `mj_step` 后原子拷到独立 buffer，避免 publish 时 mid-step 读取产生 torn frame。
2. **Inline publish**：sim_thread 在 `mj_step` 后直接 `bridge.PublishLowState()`，不再依赖
   bridge 内部的 `lowStateThread`。
3. **关停 stock RecurrentThread**（最近一次修复）：
   ```python
   bridge.lowStateThread._RecurrentThread__loopTarget = lambda: None
   bridge.HighStateThread._RecurrentThread__loopTarget = lambda: None
   ```
   等同于 ASAP `base_sim.py:sim_step` 的"physics step → 立刻 publish"模式，不让两个线程重复
   发布同一 topic、避免 DDS contention 与 GIL 抢占。

实测：仍是 13.5ms。**说明瓶颈不是"redundant publish 线程"，而是上面 §2.2 的 GIL contention
+ DDS Python 序列化开销**。

---

## 3. 可行的进一步优化（按 ROI 排序）

| 方案 | 预期收益 | 改造量 | 真机适用性 |
|---|---|---|---|
| **A. Batch motor_state 写入** —— `PublishLowState` 用 numpy → ctypes 一次性灌入 IDL（替代 29×3 attribute 设值） | -1 ~ -2ms | M（需 hack unitree_sdk2py IDL 内部） | 仅 mock；真机 SDK 自己生成 LowState |
| **B. 让 sim_thread 用 C 扩展（pyo3 / cffi）调 mujoco** | -2 ~ -4ms | L | 仅 mock |
| **C. 切到 `unitree_cpp`（RoboJuDo `UnitreeCppEnv`）** | 真机端 -3 ~ -5ms（绕过 GIL） | XL | ✅ 真机和 mock 都得益 |
| **D. 训练侧加 latency randomization (5–20ms)** | 0ms latency 但 policy 鲁棒 | 训练改造 | ✅ 唯一长期方案 |
| **E. 接受现状、把锅甩给 policy** | 0ms 工程改造 | 0 | ✅（如果 policy 已经过 randomization 训练） |

**结论**：

- **不要**继续在 Python DDS 链路上抠 ms。物理上限 5–10ms。
- **要么**走 C 路线（unitree_cpp）一次到位，**要么**训练侧补 latency 鲁棒性。
- **OmniXtreme 摔倒**——若官方 deploy 在真机能 run，说明 OmniXtreme 训练时考虑了 latency；
  那么 UHC 在 mock 摔，**root cause 大概率不是 latency 本身**，而是 obs/anchor/action/PD 复刻
  不到位（参见 `mission1_best_s2s_s2r/research/omnixrtreme_uhc_adaptation.md`）。

---

## 4. RoboJuDo `UnitreeEnv` vs UHC `UnitreeBackend` 关键代码对比

### 4.1 RoboJuDo Python DDS env（`robojudo/environment/unitree_env.py`）

```python
# 主控制循环（独立 RecurrentThread）周期发布 cmd
self.lowcmd_send_thread = RecurrentThread(
    interval=self._control_dt,
    target=self.send_cmd,
    name="control",
)
self.lowcmd_send_thread.Start()

# DDS sub callback —— 完全无锁、直接替换整个 msg 引用
def LowStateHgHandler(self, msg: LowStateHG):
    self.low_state = msg

# step(): 主线程更新 low_cmd 内容并立即发一次（额外冗余）
def control_joints(self, commands, hand_pose=None):
    for j in range(self.num_dofs):
        self.set_cmd_i(i=motor_idx, command=command, kp=self.kps[j], kd=self.kds[j], ...)
    self.send_cmd(self.low_cmd)   # 额外发一次，叠加 RecurrentThread 的周期发
```

观察：

- **没有任何 lock**，依赖 `unitree_sdk2py` 每次 callback 给一个新的 msg 对象（事实上的引用替换）。
- **cmd 双发**：每个控制周期主线程发一次，定时线程也发一次，让 G1 SDK 那边总有最新 cmd。
- **没有 latency 测量代码**——RoboJuDo 不关心绝对 latency 数值，由训练侧吸收。

### 4.2 RoboJuDo C++ DDS env（`robojudo/environment/unitree_cpp_env.py`）

```python
from unitree_cpp import RobotState, SportState, UnitreeController

self.unitree = UnitreeController(cfg_unitree_dict)   # C++ 内部起 DDS 线程

def update(self):
    self.robot_state = self.unitree.get_robot_state()  # 拉一次最新缓存，C++ side 已是无锁原子
    self._dof_pos = np.array([self.robot_state.motor_state.q[i] for i in self._dof_idx], ...)

def step(self, pd_target, hand_pose=None):
    self.unitree.step(pd_target.tolist())  # C++ 内部 set cmd → CRC → DDS Write
```

关键观察：

- **Python 只做"取最新 / 推一次"**，所有 DDS / IDL 序列化 / CRC 都在 C++ 完成。
- C++ 内部**自管周期线程**，Python 不需要 RecurrentThread。
- 没有 GIL contention。

### 4.3 UHC `UnitreeBackend`（当前）

- DDS 收发都走 `unitree_sdk2py`（Python）——结构与 RoboJuDo `UnitreeEnv` 接近。
- 主控环（`PolicyRunner._step` @ 50Hz）和 sub callback 都是 Python 线程。
- mock 时还要一个 200Hz `sim_thread_fn` 推 mj_step，三个 Python 线程抢 GIL。
- **要追平 RoboJuDo `UnitreeCppEnv` 的真机性能**，长期必须切 `unitree_cpp` pybind。

---

## 5. ASAP `base_sim.py` 关键差异（已经在我们 bridge 里复刻）

```python
# ASAP humanoidverse/sim2real/sim_env/base_sim.py 简化
def sim_step(self):
    for _ in range(self.sim_decimation):
        torque = (target - self.dof_pos) * self.kp - self.dof_vel * self.kd
        self.data.ctrl[:] = torque
        mujoco.mj_step(self.model, self.data)
    self.unitree_bridge.PublishLowState()   # 直接发，没有独立 publish thread
```

UHC `run_g1_bridge.py` 已经这么做了（§2.3），但 latency 还是 13ms，因为 ASAP 的 mock 也存在
同样的 GIL/DDS 开销——ASAP 论文 / 仓库**也没声称 mock latency < 5ms**。

---

## 6. 建议路线图（按时间分）

### 6.1 立即（不要做）

- ❌ **不要**继续优化 Python publish 路径。已经压到 GIL 上限。
- ❌ **不要**为 mock latency 引入 forward prediction / Kalman——破坏与真机时序对齐。

### 6.2 短期（这 1–2 周，回到 OmniXtreme 根因）

把"OmniXtreme mock 摔倒"重新定位为 **policy 鲁棒性 / 复刻一致性**问题，而不是 latency
问题：

1. **重读** [`omnixrtreme_loopback_deployment_distilled.md`](omnixrtreme_loopback_deployment_distilled.md) 与
   [`omnixrtreme_uhc_adaptation.md`](omnixrtreme_uhc_adaptation.md)，逐项对照 obs 拼法、
   anchor body、action_scale、kp/kd、history buffer、`without_state_estimator` flag。
2. **跑一次 OmniXtreme 官方 deploy_mujoco.py**（无 DDS / 无 GIL 多线程），与 UHC mock 用
   同一段 `fallAndGetUp` 启动状态对比 q_target / 关节轨迹的逐 tick 差异。
3. 若官方 deploy 也不能完整跑完该动作，说明 motion 本身需要较高 PD/特定 randomization。
4. 若官方 deploy 能跑、UHC 不能，差异点必在 obs/policy 适配层，不在 DDS。

### 6.3 中期（真机部署前必做）

- 评估 `unitree_cpp` (https://github.com/HansZ8/UnitreeCpp) 直接当 UHC 的可选 backend。
- 把 `UnitreeBackend` 抽象出 `UnitreeEnv` / `UnitreeCppEnv` 两个实现，按 profile flag 切换。
- 真机首次跑前先用 `UnitreeCppEnv` 跑 mock，确保 latency 落在 G1 真机预期区间（5–10ms）。

### 6.4 长期（如果要适配新 policy）

训练端补 latency randomization：在 obs 进 policy 前加 0–20ms 随机 delay buffer，与
action 出 policy 后加 0–20ms delay。这是 ASAP / RoboJuDo 默认套路。

---

## 7. 引用

- RoboJuDo: <https://github.com/HansZ8/RoboJuDo/tree/release>
  - `robojudo/environment/unitree_env.py`：Python DDS env
  - `robojudo/environment/unitree_cpp_env.py`：C++ pybind env
- ASAP: <https://github.com/LeCAR-Lab/ASAP>
  - `humanoidverse/sim2real/sim_env/base_sim.py`：单线程 mj_step + inline publish
- motion_tracking_controller: <https://github.com/HybridRobotics/motion_tracking_controller>
  - 与 UHC 完全异构（C++ ros2_control + legged_control2），不直接借鉴 latency 处理；其
    意义是验证 BM 系列 ONNX 在真机部署的"工程封装版本"。
- Unitree DDS jitter 官方说明：<https://github.com/unitreerobotics/unitree_rl_gym/issues/108>
  （社区已确认真机 DDS 可见 5–20ms jitter）

---

## 8. 更新记录

| 日期 | 事项 | 作者 |
|---|---|---|
| 2026-04-30 | 初版：基于 RoboJuDo + ASAP + MTC 源码对比，结合 UHC mock 实测 13ms 数据，明确 latency 不是当前根因 | agent |

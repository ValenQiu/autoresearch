# RoboJuDo Teacher Distilled

> **目的**：把 `https://github.com/HansZ8/RoboJuDo`（release branch）对 UHC sim2real
> 实际有用的工程决策抽成一张"决定怎么写代码"的表。**不是 paper summary**。
> 每次在 UHC 里接入新策略、或者在 mock/真机部署上 debug policy OOD 时，先读这个文件。
>
> 对应 skill：[`.cursor/skills/robojudo-policy-adaptation/SKILL.md`](../.cursor/skills/robojudo-policy-adaptation/SKILL.md)
>
> 更新规则：**只加决策和反例，不加赞美**。

---

## 1. RoboJuDo 的架构（我们要抄的那部分）

三层解耦：

| 层 | 接口数据 | RoboJuDo 里的命名 | 对应 UHC |
|---|---|---|---|
| **Controller** | 外部输入 → `ctrl_data` | `JoystickCtrl`, `UnitreeCtrl`, `MotionH2HCtrl`, `BeyondmimicCtrl` | `PolicyRunner` + keyboard/joystick 映射 |
| **Environment** | 传感器数据 `env_data` + 发执行命令 | `MujocoEnv`, `UnitreeEnv`（`unitree_sdk2py`）, `UnitreeCppEnv`（pybind） | `MujocoBackend`, `UnitreeBackend`（mock/real） |
| **Policy** | `env_data`+`ctrl_data` → action | `UnitreePolicy`, `AmoPolicy`, `BeyondMimicPolicy`, `AsapPolicy`, ... | `uhc/policies/*.py` |

**关键工程纪律（UHC 对照）**：

1. **Policy 不直接读 MuJoCo 内部 API**。所有物理状态必须走统一 `env_data`/backend API；
   这样切 Mujoco ↔ Unitree 时 Policy 代码零改动。
   - UHC 对等物：`backend.read_state()` + `backend.get_body_frame(name)`。凡是 policy 里
     `isinstance(backend, MujocoBackend)` 或者直接 `mj_data.xxx` → **红旗**。
2. **Controller 只生产 command，不改 state**。按键 `[ ] ; '` 等切换语义写在 Controller/Runner，
   policy 只暴露"允许哪些 command"。
3. **多策略切换靠 pipeline**（RoboJuDo 的 `LocoMimicPipeline`），Locomotion 作为 backup，
   Mimic 作为 task，支持插值过渡。UHC 已有同构件 (`PolicyRunner.State` + `interpolation`)。

---

## 2. BeyondMimic 部署的决定性差异（当前 debug 根因）

> **一句话**：RoboJuDo 默认加载的是 **WoSE**（Without State Estimator）版本的 BM ONNX，
> 而 UHC 当前加载的是 **With-SE** 版本。两者 obs 维度和 train-time 分布都不同。

### 2.1 两个 env config

BM 原仓库 (`whole_body_tracking`) 提供两种训练入口：

| Env config | obs 维度 | 训练时 state source | 部署可行性 |
|---|---|---|---|
| `G1FlatEnvCfg` (With-SE) | 160 | 依赖 `state_estimator`（ROS2 controller，融合 IMU+encoder+contact） | **需要**在 deploy 端也有 SE |
| `G1FlatWoStateEstimationEnvCfg` (WoSE) | 154 | obs 里**移除** `motion_anchor_pos_b` + `base_lin_vel` | **无需** SE，零 infra 部署 |

### 2.2 obs 拼法（`robojudo/policy/beyondmimic_policy.py::get_observation`）

```python
obs_prop = np.concatenate([
    obs_command,                                                      # 58
    obs_motion_anchor_pos_b if not self.without_state_estimator else [],  # 3 / SKIP
    obs_motion_anchor_ori_b,                                          # 6
    obs_base_lin_vel        if not self.without_state_estimator else [],  # 3 / SKIP
    obs_base_ang_vel,                                                 # 3
    obs_joint_pos_rel, obs_joint_vel_rel, obs_last_action,            # 29×3
])
```

RoboJuDo 默认 `without_state_estimator=True`。

### 2.3 `override_robot_anchor_pos`（第二道兜底）

当 ONNX 是 With-SE 但部署端**没有** state estimator（= 我们当前 loopback/mock 情况），
RoboJuDo 允许 `override_robot_anchor_pos=True`：

```python
if self.override_robot_anchor_pos:
    robot_anchor_pos_w = anchor_pos_w.copy()   # = motion anchor
else:
    robot_anchor_pos_w = env_data.torso_pos    # = 真实躯干世界位置

robot_anchor_quat_w = env_data.torso_quat
```

- **效果**：`obs_motion_anchor_pos_b == 0`（position 差归零），但 `obs_motion_anchor_ori_b`
  仍按 `env_data.torso_quat` 算，保留 rotation 对齐误差信号。
- **直觉**：当你没法可靠估计 torso 世界位置时，宁可让 policy 以为"位置完美对齐"
  也不要喂垃圾值；但**方向**对平衡至关重要，用 IMU+FK 估的值是可信的。

### 2.4 ONNX metadata 驱动的 obs 布局

RoboJuDo 读 ONNX `custom_metadata_map` 自动覆写：`joint_names, default_joint_pos,
joint_stiffness, joint_damping, action_scale, anchor_body_name, body_names,
observation_names`。UHC 已经抄了前几项，**但之前没读 `observation_names`** —— 这是
WoSE/With-SE 自动分流的关键。

---

## 3. UHC 当前的对齐状态

### 3.1 已采纳（2026-04-23）

| RoboJuDo 决策 | UHC 实现 |
|---|---|
| obs 按 `observation_names` metadata 动态拼 | `uhc/policies/beyondmimic.py::_build_obs` — 2.2 复刻 |
| `without_state_estimator` 从 metadata 自动推断 | `BeyondMimicPolicy._without_state_estimator` |
| `override_robot_anchor_pos` | profile 字段，loopback 默认 `True`；见 `sim2real_g1_loopback_bfm_bm.yaml` |
| Controller/Env/Policy 三层解耦 | `PolicyRunner` + `MujocoBackend`/`UnitreeBackend` + `uhc/policies/*` |
| 多策略切换 + 插值过渡 | `PolicyRunner.State` + `interpolation.loco_to_task_duration_s` |

### 3.2 未采纳 / 待办

| RoboJuDo 决策 | UHC 现状 | 处理方式 |
|---|---|---|
| 默认 WoSE ONNX | 用户当前 ONNX 是 With-SE（`obs: [1, 160]`） | **P4 TODO**：在 MTC / `whole_body_tracking` 里切 `G1FlatWoStateEstimationEnvCfg` 重训导出 WoSE ONNX |
| `UnitreeCppEnv`（pybind 替代 Python DDS） | UHC 用 `unitree_sdk2_python` Python DDS | 真机稳定性不达标时再做 |
| `state_estimator`（contact-aided pelvis pose） | UHC 只有 C1 constant-z + IMU quat + waist FK | P2+ 的长期事项；真机部署前必须做 |
| 工程化单元："一个策略一条 profile" | UHC 已有同构做法（`config/profiles/*`） | ✅ |

---

## 4. UHC 接入新策略的 checklist（抄自 RoboJuDo 行为）

1. **读 ONNX metadata 先**：
   ```python
   meta = sess.get_modelmeta().custom_metadata_map
   for k in ("joint_names", "default_joint_pos", "joint_stiffness",
             "joint_damping", "action_scale", "body_names",
             "anchor_body_name", "observation_names"):
       print(k, meta.get(k))
   ```
   → 所有 per-joint 量和 obs 布局**不能 hardcode**。
2. **obs 布局动态化**：用 `observation_names` 驱动分段拼接，不按维度总数切分。
3. **anchor body 的世界位姿**：必须走 `backend.get_body_frame(anchor_body_name)`，
   Mujoco 返回 GT，Unitree 返回 IMU+FK 估计值；policy 自己不做 `isinstance`。
4. **对"没有 state estimator"的部署路径**：
   - 如果 ONNX 有 WoSE 版本 → 优先用。
   - 否则 → 在 profile 打开 `override_robot_anchor_pos: true`（position 置零）+
     保留真实 torso_quat（IMU+FK）。
   - 最终长期方案：deploy 端实现 state estimator。
5. **写 selftest**：headless + 显式 PASS/FAIL，判据至少包含 tilt 阈值、|qd|max、
   q_target 跳变、pelvis_z。参考 `scripts/smoke_task_loopback.py`。

---

## 5. 部署时序：`passive → recovery → task`（mock / 真机通用）

> **规则**：UHC 的 loopback mock 与真机部署**必须**走同一个三段流程。`smoke_task_loopback.py`
> 的时序是这份定义的**单一真源**；任何和它不一致的 profile 注释 / 文档都是 stale。

### 5.1 三段时序

| 阶段 | 物理状态 | PolicyRunner 状态 | 触发方式（人工 / headless） |
|---|---|---|---|
| **passive** | 弹力绳 ON 悬挂 → SIGUSR1/`9` drop → 机器人瘫倒在地，零力矩 | `State.PASSIVE`（`_step` 写 `kp=0,kd=0,q_target=cur`） | bridge 启动自动 passive；按 `9` 或 `SIGUSR1` 掉绳；等物理稳定（~1.5 s） |
| **recovery** | BFM-Zero 作为 whole-body controller 从趴姿起身 | `INIT` 把状态机推到 `BASE_ACTIVE` → 下一 tick `ACTIVATE_TASK` 把 `_policy_active` 置真、强制清 `_init_active`（`policy_runner.py::_handle_event`，line ~530）；BFM-Zero `safety_min_height=0` 允许贴地恢复 | 人工：`i` → `]`（紧挨着）；headless：`Event.INIT` → 次 tick `Event.ACTIVATE_TASK` |
| **task** | BeyondMimic（或其他 task policy）接管 | `BASE_ACTIVE` → `TASK_ACTIVE`，触发 `_begin_enter_task` 走 upper-body interp | 人工：`[`；headless：`Event.SWITCH_TO_BASE` |

### 5.2 "recovery 站稳了吗"的判据（headless 唯一口径）

`scripts/smoke_task_loopback.py` 里的稳定门，**不靠 wall-clock 等一段时间**，而是对连续 tick 检测：

```
tilt(deg) < --recovery-tilt-max-deg   (默认 15°)
max|joint_vel|(rad/s) < --recovery-qd-max  (默认 1.0)
两者同时满足连续 --recovery-stable-sec 秒（默认 2.0 s）
```

从 `]` 开始 `--recovery-timeout-sec`（默认 8 s）之内仍未满足 → **FAIL**（不会继续进 task）。

**为什么不是固定 `sleep 3s`**：不同 goal z 的起身时长差别大（`fallAndGetUp1_subject4_2193` 有时要 4 s，plain T-pose 只要 1 s）；用固定 sleep 就要么过度保守浪费时间，要么未收敛就进 task，两者都掩盖真实故障模式。

### 5.3 为什么这和旧版 `i → ] → 9 → [` 不同

旧版 smoke 的时序：band **ON** 悬挂期间跑 `i`（插到 default pose，假设脚能着地）、`]`（激活 BFM-Zero 当 loco，假设已经站立）、然后才 `9` drop band、`[` 进 task。

这违反真实部署：**真机不会先吊着机器人假装它已经站好再放绳**。真机是"机器人趴在地上 → 操作者按 `]` 让 BFM-Zero 帮它站起来 → 站稳了再按 `[` 进 task"。

所以现在：band 一启动就 drop（passive），让 BFM-Zero **必须从 crumpled 姿态 recovery 到 standing**，才算真正覆盖真机场景。mock 里 recovery 都过不了，真机上必然过不了。

### 5.4 `--cycle-before-enter` 的含义

recovery 用**默认 goal z**（`bfm_zero.yaml::z_sources.default`）即可，不需要 cycle。
`--cycle-before-enter n|p|t` 只在**验证特定 goal z 的稳定性**时用，插在"recovery 稳定"与"进 task"之间。

---

## 6. DDS / latency / 线程模型（2026-04-30 补）

> **背景**：UHC sim2real mock 链路实测 round-trip 13ms，OmniXtreme 在地面接触动作处摔倒。
> 一度怀疑 latency 是根因。读 RoboJuDo `UnitreeEnv` / `UnitreeCppEnv` 源码后修正认知，
> 完整对比与建议路线：[`sim2real_latency_analysis.md`](sim2real_latency_analysis.md)。

### 6.1 RoboJuDo 提供两条 env 实现，分别对应 Python DDS / C++ DDS

| Env class | DDS stack | 线程模型 | 取舍 |
|---|---|---|---|
| `UnitreeEnv`（`unitree_env.py`） | `unitree_sdk2py`（Python） | `RecurrentThread(send_cmd, interval=control_dt)` 周期发；DDS sub callback 在 sdk 内部线程；`step()` 主线程**额外 send 一次**（双发冗余） | 容易上手；GIL 限制实测 round-trip ≥ 5ms |
| `UnitreeCppEnv`（`unitree_cpp_env.py`） | `unitree_cpp` pybind11 包装 unitree_sdk2 C++ | DDS 全部在 C++ 线程，Python 只 `unitree.step(target)` / `unitree.get_robot_state()` | 真机首选；绕过 GIL；单点风险是 cpp 编译/部署 |

RoboJuDo README 明文说："**Light-Weight: By UnitreeCpp, RoboJuDo runs on Unitree G1 without
the need for an Ethernet cable.**"——onboard 跑要的是 C++ DDS。

### 6.2 RoboJuDo 关键工程决定（要抄）

1. **DDS sub callback 不加锁，直接替换整个 msg 引用**：
   ```python
   def LowStateHgHandler(self, msg: LowStateHG):
       self.low_state = msg
   ```
   依赖 `unitree_sdk2py` 每次 callback 给独立 msg 对象。UHC 的 `UnitreeBackend` 同款，没问题。
2. **cmd 双发**：定时线程按 `control_dt` 发一次、主线程 `step()` 立即再发一次。即使主线程
   被阻塞，定时线程也保证 G1 SDK 不超过 control_dt 看不到新 cmd。**UHC 当前没双发**，但目前
   PolicyRunner 的 50Hz tick 已自带稳定节拍，等真机部署再看是否需要补冗余发。
3. **没有 latency 测量代码**：RoboJuDo 不在 deploy 端关心绝对 latency。一致延迟由训练侧
   (domain randomization) 吸收。这正是我们在 `sim2real_latency_analysis.md §3` 得到的结论。
4. **deploy 端不做 forward prediction / Kalman state estimator**：如果 ONNX 训练时有 SE，
   就在 deploy 端实现 SE；如果训练时是 WoSE，就让 deploy 端用 `override_robot_anchor_pos`
   把 anchor 位置归零。**没有任何"主动补偿 DDS 抖动"的逻辑**。

### 6.3 UHC 对照状态

| RoboJuDo 决策 | UHC 现状 | 差距 / TODO |
|---|---|---|
| 提供 Python DDS env (`UnitreeEnv`) | `UnitreeBackend` ✅ | 已对齐 |
| 提供 C++ DDS env (`UnitreeCppEnv`) | ❌ | **真机部署前 P2**：评估接入 `unitree_cpp` 作 UHC backend |
| sub callback 无锁、msg 引用替换 | ✅ | 已对齐 |
| cmd 双发冗余 | ❌（PolicyRunner 单发） | 真机首跑前补 |
| deploy 端不做 latency 补偿 | ✅ | 已对齐 |
| 训练侧 latency randomization | 训练不在 UHC 仓库 | OmniXtreme 训练复盘时确认（已在 sim2real_latency_analysis §6.4） |

### 6.4 mock 链路自身的优化（已做 / 不再做）

| 优化 | 是否完成 | 评估 |
|---|---|---|
| `mj_data` snapshot under lock，避免 `PublishLowState` 与 `mj_step` 数据竞争 | ✅ `tools/loopback_bridge/run_g1_bridge.py` | 必要的正确性修复 |
| `sim_thread` 内 inline `bridge.PublishLowState()`（仿 ASAP `base_sim.py:sim_step`） | ✅ | 必要 |
| 关停 bridge stock `lowStateThread` / `HighStateThread` 的 `RecurrentThread`（避免双发竞争） | ✅ | 必要 |
| 继续在 Python publish 链路抠 ms（ctypes batch、cffi 替换属性赋值等） | ❌ **不做** | ROI 低；GIL 是物理上限 |

### 6.5 给到将来 agent 的红旗清单

进入 sim2real / mock / 真机 debug 时，看到下列**任何**情况就**先对齐基础项再讨论 latency**：

- 摔倒发生在 dynamic / 接触阶段（如 OmniXtreme 着地段、ASAP 翻滚段），且
- 同一 motion 在官方 deploy 能跑通 →
  **几乎一定不是 latency**，而是 obs 拼法 / anchor 处理 / action_scale / PD / friction 复刻
  问题。先对照 `mission1_best_s2s_s2r/research/<policy>_uhc_adaptation.md`、
  `research/<policy>_loopback_deployment_distilled.md` 的逐项 checklist，跑通官方 deploy
  在同一 mock 上的对照实验。

---

## 7. 参考链接

- 仓库（release branch）：<https://github.com/HansZ8/RoboJuDo/tree/release>
- 文档：`docs/policy.md`（BeyondMimicPolicy / AsapPolicy / ProtoMotionsTrackerPolicy）
- BM 源码：`robojudo/policy/beyondmimic_policy.py`
- env 源码：`robojudo/environment/{unitree_env.py,unitree_cpp_env.py,mujoco_env.py,base_env.py}`
- env_data 接口：`robojudo/environment/base_env.py::EnvData`
- BeyondMimic 原作：<https://github.com/HybridRobotics/whole_body_tracking>
- ASAP 原作：<https://github.com/LeCAR-Lab/ASAP>（`humanoidverse/sim2real/`）
- MTC（HybridRobotics 原作）：<https://github.com/HybridRobotics/motion_tracking_controller>
  ——C++ ros2_control 实现，与 UHC 异构，仅供 BM 部署封装参考；早期复盘
  [`mission1_best_s2s_s2r/research/motion_tracking_controller_postmortem.md`](../mission1_best_s2s_s2r/research/motion_tracking_controller_postmortem.md)
  讨论的是 dummy_task fork 而非该原始仓库
- UnitreeCpp（RoboJuDo 用的 C++ pybind）：<https://github.com/HansZ8/UnitreeCpp>
- latency 专题：[`sim2real_latency_analysis.md`](sim2real_latency_analysis.md)

---

## 8. 更新记录

| 日期 | 事项 | 作者 |
|---|---|---|
| 2026-04-23 | 初版：从 RoboJuDo release 文档 + `beyondmimic_policy.py` 提炼；锚定于 UHC BM 摔倒根因 debug | agent |
| 2026-04-23 | 加 §5：固化 `passive → recovery → task` 部署时序 + headless 稳定判据，纠正 `smoke_task_loopback.py` 之前假设"机器人已站"的 `i → ] → 9 → [` 旧时序 | agent |
| 2026-04-30 | 加 §6：从 `unitree_env.py` / `unitree_cpp_env.py` 抽取 DDS / latency / 线程模型决策；标注 UHC 对齐状态、TODO（unitree_cpp backend）、与 mock 链路停止抠 ms 的工程结论；与 `sim2real_latency_analysis.md` 配套 | agent |

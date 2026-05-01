# OmniXtreme vs ASAP Mimic / BeyondMimic：为何 Omni 在 UHC 中更难部署（技术对照报告）

本文面向：**已在 mock / sim2sim 中验证 ASAP Mimic、BeyondMimic（BM）切换顺畅，但 OmniXtreme（Omni）路径仍摩擦很大**的场景。  
结论先行：**不是「Omni 模型更弱」，而是 Omni 在观测构造、参考运动、执行链路与闭环特性上对部署误差极度敏感**；Mimic/BM 在工程上把大量复杂度「收口」到单 ONNX + 更温和的观测形态里。

---

## 1. 执行拓扑：三者共同点与 Omni 额外暴露的面

| 维度 | ASAP Mimic | BeyondMimic | OmniXtreme |
|------|------------|-------------|------------|
| **sim2sim（MuJoCoBackend）** | 状态来自仿真本体，`get_body_frame` / `body_x*` 齐全 | 同上；锚点对齐可走权威 body frame | 同上；另需 **FK / initial_yaw / command_obs** 与参考 `.npz` 对齐 |
| **mock（UnitreeBackend + DDS + bridge）** | 观测主要来自 **LowState + 可选 SE**；相位只用本地 `step_count` | 观测依赖 **锚点世界位姿**；mock 下若缺 body frame 会走 **保守 fallback**（`base_pos` + I） | 除 LowState 外，**command_obs / anchor / 历史缓冲** 任一与参考不一致 → FM 输出偏离；**异步 DDS ~10ms** 对 **高动态 + 双网络** 更敏感 |
| **参考运动来源** | **不显式外部轨迹文件**；相位标量 `phase∈[0,1]` 驱动 | **ONNX 多输出** 自带 `joint_pos`/`body_pos_w` 等参考 | **外部 `motion.npz` + MotionReferenceSource**；与 Base/Residual **关节顺序混用（BM vs URDF）** |

**要点**：Mimic/BM 在 mock 上「顺畅」，通常意味着 **观测里的锚点/相位误差尚未越过策略容忍带**；Omni 的 **90 维 real_obs + 15×90 历史 + 64 维 command_obs** 把误差放大成 **高维分布偏移（OOD）**。

---

## 2. 策略形态：单策略 vs「FM + Residual + 外部运动」

### 2.1 ASAP Mimic（`uhc/policies/asap_mimic.py`）

- **网络**：单个 ONNX，`raw_action → action_scale → + default → q_target`。
- **观测**：`last_action(掩码)`、`base_ang_vel`、`dof_pos_err`/`dof_vel`(掩码)、可选 history、`projected_gravity`、**标量 phase**。
- **相位**：`phase = step_count / (motion_length_s * hz)`，**只依赖本地计数**，与 DDS 延迟弱耦合。
- **自由度**：可按输出维数自动 **DOF mask**（如 23-DOF 关掉手腕），降低末端噪声耦合。
- **切换**：`get_first_frame_upper_target()` 用「phase=0 的一次伪推理」生成上肢插值目标，并对腰滚/腰俯做归零处理，减少切入扭曲。

**工程特征**：闭环里 **没有「第二条轨迹源」**；参考意图集中在 **单一 phase 通道**，对锚点、FK、外部 npz 同步要求低。

### 2.2 BeyondMimic（`uhc/policies/beyondmimic.py`）

- **网络**：单个 ONNX，**双输入**（`obs` + `time_step`），**多输出**（actions + reference motion）。
- **参考**：每步从 ONNX 解析 `_ref_joint_pos/_ref_body_pos_w/...`，与策略 **同一前向传播绑定**，不存在「UHC 侧另一份 npz 与 ONNX 漂移」问题。
- **观测**：由 ONNX metadata `observation_names` 驱动 **With-SE / Wo-SE** 布局；`override_robot_anchor_pos` 仅改观测语义。
- **对齐**：`_compute_world_to_init` 做 **yaw-only** 运动坐标系对齐；优先 `backend.get_body_frame`。
- **切换**：profile 里常用 `override_robot_anchor_pos: false` + mock SE，使 **锚点误差来自估计器而非强行填零**，长相位更稳。

**工程特征**：**参考与控制共推理**；外部文件主要是训练资产同步（wandb/npz），运行时主路径仍是一份 ONNX。

### 2.3 OmniXtreme（`uhc/policies/omnixrtreme.py`）

- **网络**：**Base ONNX（FM）+ Residual ONNX + 可选 FK ONNX**。
- **参考**：**独立 `motion.npz`**，由 `MotionReferenceSource` 按帧读取；**command_obs（64 维）** 依赖参考帧与 **FK（anchor 6D）**。
- **观测（Base）**：
  - `real_obs`（90）：关节位置/速度（相对 default）、base 角速度、`prev_action` 等（与 deploy 对齐的缩放/噪声）。
  - `real_historical_obs_raw`：**15 帧 × 90 维** FIFO；**历史任一帧 OOD → 后续 FM 持续恶化**。
  - `command_obs`（64）：来自 **当前参考帧 + FK**，与 **锚点 body、`initial_yaw` Latch 顺序**强相关。
  - `initial_noise`：FM 输入噪声模式（per_step / per_episode / zero）。
- **动作**：`raw = a_base + residual_gain_eff * map(a_res)`，再 **`action_scale` + default**，再 **电机包络裁剪 + 摩擦补偿**（与 `deploy_mujoco.py` 一致的参数表 `_X1_LIST` 等）。
- **额外机制**：`entry_align_enabled`、`history_warm_start`、`pre_settle_ticks`、`residual_guard`、`q_target_slew_rate`、`task_entry_stabilize_*`、`freeze_at_frame` 等——每一项都是在补 **「分布对齐」与「执行链不一致」**。

**工程特征**：Omni = **两条网络 + 外部参考 + 长历史 + 非线性执行模型**；任何一个环节与原生 deploy 不一致，都会在 **残差支路** 被放大。

---

## 3. 为何 Mock 里 Mimic/BM「顺」，Omni「难」——机制拆解

### 3.1 观测维度与误差放大

- **Mimic**：相位一维 + 掩码关节；历史若有也是 **按掩码裁剪**，有效维度更低。
- **BM**：观测布局固定来自 metadata，闭环主要敏感 **锚点/对齐**；你已用 SE + `override_robot_anchor_pos: false` 把大问题收口。
- **Omni**：**1350 维历史 + 90 维当前 + 64 维 command**，且 **Residual 另吃 183 维**。  
  mock 下常见微小差异包括：**初始 yaw latch 顺序**、**FK 输入腰关节索引**、`command_obs` 与 `real_obs` 时间对齐（DDS 一步延迟）、`prev_action` 与 PD 实际跟踪误差。  
  这些在 Mimic 里可能被 phase/gravity 平滑掉，在 Omni 里会进入 **history**，形成 **自激偏离**。

### 3.2 参考运动的「绑定方式」

- **BM**：参考 **跟 ONNX 同步生成**，不存在「npz 帧索引与 step_count 偏移」类问题。
- **Omni**：参考 **纯外部文件**；`reset()` 时 `step_count = _entry_start_frame`，`MotionReferenceSource.reset(start_frame=...)`。  
  若切入任务时 **机体姿态/速度与参考帧语义不一致**（例如 recovery 站立 vs clip 当前帧），则 **command_obs 已偏**，FM 为纠错会输出大动作 → 与 Mimic「仅靠 phase」相比更难调。

### 3.3 执行链：包络 + 摩擦 + skip_position_clip

- Omni 在 UHC 中显式实现 **扭矩-速度包络** 与 **摩擦补偿**（见 `omnixrtreme.py` 顶部说明与 `_apply_actuator_model`）。  
  **原生 MuJoCo 一步内多 substep** 与 **mock 桥 + 50Hz 命令** 的交互下，**同一 raw 目标经包络后的有效目标** 可与 sim2sim 有细微差别；对 ** fall/getup 高动态** 更致命。
- Mimic/BM：**无这一条与 deploy 逐行绑定的包络链**（或弱化），对「命令层面的微偏差」不敏感。

### 3.4 双网络耦合（FM + Residual）

- **Residual 专门弥补 FM 的系统性偏差**；若观测或参考稍有 OOD，Residual 会输出 **大方差修正**。  
  在 mock 延迟与历史污染存在时，容易出现 **base/res/raw 范数交替飙升**（你在 audit log 里见过的模式）。
- Mimic/BM：**单网络直接回归目标**，没有「第二条腿」把误差放大成对抗性修正。

### 3.5 任务切换与基座策略交互

- PolicyRunner 对 **Omni** 往往配合 **BFM-Zero / ASAP Loco** 等不同 recovery；**腰角、踝角、COM** 与 Omni frame0 期望不一致时，需要 **整身上肢插值 / 可选下肢插值 / pre-settle / entry_align** 等补丁。  
- Mimic：**phase 驱动**，上半身目标可由「phase=0 伪推理」近似；BM：**锚点与世界对齐**在后端可靠时一次搞定。  
  Omni：**既要对齐关节空间，又要对齐 command_obs 里的运动学量**，难度更高。

### 3.6 训练侧随机化 vs 部署侧确定性

- Omni 原生 deploy 常见 **动作延迟随机化（substep 内随机施加时刻）** 等域随机；纯粹确定性 mock **不在训练分布中心**。  
- Mimic/BM 对此依赖通常较弱（仍可能有随机化，但观测通道更少、耦合更松）。

---

## 4. UHC 实现映射（便于你逐文件对照）

| 组件 | ASAP Mimic | BeyondMimic | OmniXtreme |
|------|------------|-------------|------------|
| 策略文件 | `uhc/policies/asap_mimic.py` | `uhc/policies/beyondmimic.py` | `uhc/policies/omnixrtreme.py` |
| 参考 | `phase` + `motion_length_s` | ONNX 输出 reference | `uhc/reference/motion.py` + `.npz` |
| 关节顺序 | ASAP 输出掩码 | ONNX metadata `joint_names` → `JointMapper` | **Base: URDF；Residual/.npz: BM 序** → `JointMapper` |
| 观测特殊 | gravity + phase | anchor / WoSE 布局 | **FK、initial_yaw、history、command_obs** |
| 执行模型 | 无包络链 | 无 Omni 同款包络 | **包络 + 摩擦** |
| Profile 典型 | `asap_mimic.yaml` + mimic ONNX | `beyondmimic.yaml` + `override_robot_anchor_pos` | `omnixrtreme.yaml` + `models/omnixrtreme/` |
| 切换敏感点 | 腰预置零 | 锚点/SE | **entry frame、腰/FK、history、ramp/guard** |

**调度层**：`uhc/core/policy_runner.py`（插值、`upper_body_ref`、可选下肢 blend、`prepare_entry_alignment`）对 **Omni** 的影响面更大。

**mock 链路**：`uhc/backends/unitree_backend.py` + `tools/loopback_bridge/run_g1_bridge.py`；Omni profile 常配 **`g1_29dof_omnixrtreme.xml` + `simulate_dt=0.004`** 与 **SE**，与 BFM/BM 文档一致。

---

## 5. 对你当前现象的合理解释（归纳）

1. **Mimic「顺」**：单 ONNX + phase；mock 延迟主要影响「跟踪手感」，不易摧毁观测分布。  
2. **BM「顺」**：参考随 ONNX；锚点在 SE + `override_robot_anchor_pos: false` 下已闭环；单网络输出目标。  
3. **Omni「难」**：**外部 npz + 双网络 + 长历史 + FK/command + 包络链**，在 **recovery→task** 与 **mock 异步** 下极易 OOD；需要 **严格对齐 deploy_mujoco 的单步语义**，并用 **对齐帧 / 噪声 / ramp / guard / 插值** 等工程手段补偿。

---

## 6. 若要继续压缩 Omni 风险（实施优先级建议）

以下为「调查报告」级建议，不要求你立刻改代码：

1. **对齐优先级**：单步 `real_obs` / `command_obs` / `history` / `prev_action` 与 `deploy_mujoco.py` **字节语义一致**（已有脚本方向：`scripts/compare_omni_deploy_obs.py`）。  
2. **切入**：明确 `_entry_start_frame` 语义（默认 0 vs entry_align）；保证 **参考帧与机体状态** 在 command_obs 上不自相矛盾。  
3. **mock**：确认 bridge 与 UHC **同 profile 物理**（xml/dt）；对比 **sim2sim vs mock** 时用同一套 Omni yaml。  
4. **审计**：保留短时 `audit_*`，对照 **base_norm / res_norm / hist_norm / qerr**，定位是参考错还是执行链错。  
5. **训练域**：若长期走确定性 mock，可考虑在仿真侧引入 **与训练一致的延迟随机化**（需在训练/config 层讨论）。

---

## 7. 参考文献（仓库内）

- Omni 策略与执行链：`universal_humanoid_controller/uhc/policies/omnixrtreme.py`  
- Mimic：`universal_humanoid_controller/uhc/policies/asap_mimic.py`  
- BM：`universal_humanoid_controller/uhc/policies/beyondmimic.py`  
- 调度：`universal_humanoid_controller/uhc/core/policy_runner.py`  
- 原生对照：`OmniXtreme/deploy_mujoco.py`  
- mock 时延与外部栈对照：[`sim2real_latency_analysis.md`](sim2real_latency_analysis.md)

---

*文档生成说明：基于当前 UHC 源码结构与既定部署讨论整理；若后续 Omni yaml / PolicyRunner 行为变更，请以代码为准更新本节「实现映射」表。*

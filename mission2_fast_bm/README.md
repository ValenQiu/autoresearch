# Mission 2：Fast BeyondMimic Training

加速 BeyondMimic 运动追踪策略的训练收敛，在**不降低最终策略质量**的前提下缩短完整训练周期。

## Milestones

每个 Milestone 产出一个**独立可训练的 Task**，可单独启动训练做消融对比，互不依赖；全部验证通过后再合并为 `M_Full`。

每个 Milestone 产出一个**独立可训练的 Task**，可单独启动训练做消融对比，互不依赖；全部验证通过后经 M_Cleanup 整理为单一干净 task，完全类比 `Tracking-Flat-G1-v0` 的简洁结构。

| ID | Task ID（训练期） | 名称 | 范围 | 状态 |
|----|------------------|------|------|------|
| M0 | `Tracking-Fast-G1-v0` | 基础设施（与 Flat 等价） | 配置基建 | **已完成**（基建可训；Flat 等价以 `selftest_fast.py` + 对照训练在计划中勾选验收） |
| M1 | `Tracking-Fast-Noise-G1-v0` | 仅课程观测噪声 | 样本效率 | **进行中**（实现已合入；**`ScaledUniformNoiseCfg` 与 Isaac `noise.func(obs, cfg)` 约定待对齐**后重跑消融方有效） |
| M2 | `Tracking-Fast-Push-G1-v0` | 仅课程 Push | 样本效率 | **进行中**（实现已合入；Walk/Dance 达标验收待补） |
| M3 | `Tracking-Fast-EarlyStop-G1-v0` | 仅自适应早停 | 计算效率 | **进行中**（仅本 task 启用早停；判据/阈值可与实验结论再调） |
| M_Full | `Tracking-Fast-Full-G1-v0` | 噪声 + Push 合并（**默认关闭早停**） | 全特性 | **进行中**（与 M1 同噪声修复依赖；早停不纳入 Full） |
| M4 | `Tracking-Fast-Assist-G1-v0` | 站立辅助力（200 N） | 早期收敛 | 待评估 |
| **M_Cleanup** | **`Tracking-Fast-G1-v0`（最终）** | **消融架构收敛 → 单一干净 task** | 代码整理 | **未开始** |

> **进度说明**：`whole_body_tracking`（`fast_bm_training`）侧 Fast task、runner、`train_fast.py`、远程 fuyao 启动链路已在工程上跑通；Mission 2 **收尾**集中在：噪声课程接线修复、WandB 正式达标对照、**M_Cleanup** 单 task 收敛与 selftest 数字对齐。  
> M_Cleanup 完成后：消融 task（Noise/Push/EarlyStop/Full）从注册表删除，feature flag 全部消除，`Tracking-Fast-G1-v0` 成为唯一对外 task，结构与 `Tracking-Flat-G1-v0` 完全对称。

## 核心规则（强制）

1. **独立配置**：所有改动通过新 task `Tracking-Fast-G1-v0` 实现，**不修改** `Tracking-Flat-G1-v0`。
2. **强度课程而非硬开关**：用连续标量 \(s(t)\in[0,1]\) 调节观测噪声与 push 幅度，不在中途开关事件。
3. **`startup` 域随机不变**：摩擦/CoM/关节 default 的 `startup` 随机化在 `load_managers()` 时一次性完成，训练中不重采；不以「关闭 startup」作为早期易化手段。
4. **自测先行**（DEVELOPMENT_RULES §1）：每个 Milestone 完成前须有可通过的 headless selftest。

## 课程与早停公式（以 iteration \(n\) 表示）

### 1) 统一线性课程函数

设课程起始强度为 `start`，warmup 轮数为 `T`，目标强度固定为 `1.0`：

\[
s(n; start, T)=
\begin{cases}
1, & T \le 0 \ \text{or}\ start=1 \\
\min\left(1,\ start + (1-start)\frac{n}{T}\right), & \text{otherwise}
\end{cases}
\]

说明：
- `start=1.0` 是哨兵值，表示该课程关闭（全程强度恒为 1）。

### 2) 观测噪声课程（Noise）

\[
s_{\text{noise}}(n)=s(n; s_{n0}, T_n)
\]

若某观测项原始噪声范围为 \([a,b]\)，则第 \(n\) 轮实际噪声范围：

\[
[a_n,b_n]=[a\cdot s_{\text{noise}}(n),\ b\cdot s_{\text{noise}}(n)]
\]

当前 Full 配置：\(s_{n0}=0.2,\ T_n=5000\)。

### 3) Push 课程（Velocity Range）

\[
s_{\text{push}}(n)=s(n; s_{p0}, T_p)
\]

若原始 push 速度范围为 \([v_{\min},v_{\max}]\)，第 \(n\) 轮实际范围：

\[
[v_{\min}(n),v_{\max}(n)] =
[v_{\min}\cdot s_{\text{push}}(n),\ v_{\max}\cdot s_{\text{push}}(n)]
\]

当前 Full 配置：\(s_{p0}=0.1,\ T_p=8000\)。

### 4) 自适应早停（Plateau）

窗口长度 \(W=\text{plateau\_window}\)，阈值 \(\tau=\text{plateau\_threshold}\)，最早检查轮次 \(n_{\min}=\text{min\_iterations}\)。

当 \(n \ge n_{\min}\) 且窗口样本已满时，计算窗口内均值奖励的线性回归斜率：

\[
\beta_n =
\frac{\sum_{i=0}^{W-1}(i-\bar i)(r_{n-W+1+i}-\bar r)}
{\sum_{i=0}^{W-1}(i-\bar i)^2},
\quad
\bar i=\frac{W-1}{2}
\]

触发早停条件：

\[
|\beta_n| < \tau
\]

**参数与 task 对应关系**（`G1FastBasePPORunnerCfg` 默认值）：\(W=1000,\ \tau=5\times 10^{-5}\)。  
- **`Tracking-Fast-EarlyStop-G1-v0`（M3）**：`min_iterations=5000`，上述 plateau 判据**会生效**。  
- **`Tracking-Fast-Full-G1-v0`（M_Full）**：`min_iterations=int(1e9)`（哨兵），早停**默认关闭**；Full 只保留噪声 + Push 课程。

## 仓库分支

| 仓库 | 分支 | 用途 |
|------|------|------|
| `autoresearch` | `mission2` | 文档、调研、计划（本目录） |
| `whole_body_tracking` | `fast_bm_training` | 代码实现 |

## 文件说明

| 文件 | 内容 |
|------|------|
| `README.md`（本文件） | Mission 总览、Milestones、核心规则 |
| `plan_fast_bm_training.md` | 严谨执行计划，含每步代码、验收标准 |
| `research/baseline_analysis.md` | 基线 Run 分析（可选独立文档；当前汇总见下文「背景 §7」） |
| `research/research_teacher_student_pretrain.md` | **插眼**：理想仿真 Teacher、部署向 Student 蒸馏、开源索引；**后续独立 Mission**，不在 Mission 2 交付范围 |

### 后续 Mission（插眼）

若要用「简化碰撞 / 理想仿真」换训练 wall-clock，再在高保真域对齐真机策略，路线与参考仓库见 [`research/research_teacher_student_pretrain.md`](research/research_teacher_student_pretrain.md)。Mission 2 仍以 **Flat 等价物理 + 课程噪声/Push** 为主，避免 scope 膨胀。

---

# 背景与调研结论

## 1. 目标

在**完全保留**现有 BeyondMimic 训练效果（最终奖励 / sim2real 品质）的前提下：
- 使收敛所需 PPO iteration **减少 ≥ 30%**（目标：30000 → ≤ 21000 iter）
- 自动检测平台期并提前结束，避免无效算力消耗

## 2. 代码仓库结构（whole_body_tracking）

```
source/whole_body_tracking/whole_body_tracking/
├── tasks/tracking/
│   ├── tracking_env_cfg.py        # 基础 TrackingEnvCfg（EventCfg / RewardsCfg / ObsCfg 等）
│   ├── config/g1/
│   │   ├── __init__.py            # Gym task 注册
│   │   ├── flat_env_cfg.py        # 现有 G1FlatEnvCfg（保持不动）
│   │   └── agents/rsl_rl_ppo_cfg.py  # PPO 超参（保持不动）
│   └── mdp/
│       ├── commands.py            # MotionLoader + MotionCommand（adaptive sampling）
│       ├── events.py              # 自定义 event（randomize_joint_default_pos / CoM）
│       ├── observations.py        # obs term 函数
│       └── rewards.py             # reward 函数
├── utils/
│   └── my_on_policy_runner.py     # MotionOnPolicyRunner（继承 OnPolicyRunner）
scripts/
└── rsl_rl/train.py                # 训练入口（下载 WandB artifact → 启动 runner）
```

**关键参数（现有基线 `Tracking-Flat-G1-v0`）：**

| 参数 | 值 |
|------|-----|
| `scene.num_envs` | 4096（本 mission 不低于此值，可到 8192） |
| `decimation` | 4（sim.dt=0.005s，控制步=0.02s） |
| `episode_length_s` | 10.0 |
| `max_iterations` | 30000 |
| `num_steps_per_env` | 24 |
| `num_learning_epochs` | 5 |
| `num_mini_batches` | 4 |

## 3. Isaac Lab v2.1.0 EventManager 行为（已从源码确认）

> **来源**：Isaac Lab 官方 tag `v2.1.0`，`manager_based_rl_env.py` + `event_manager.py`

| mode | 何时触发 | 触发者 | 触发次数 |
|------|----------|--------|---------|
| `prestartup` | 仿真 `play()` **之前** | `ManagerBasedEnv.__init__` | 1 次 |
| `startup` | 所有 Manager 建好后（`load_managers()` 末尾） | `ManagerBasedRLEnv.load_managers` | **整个进程 1 次**，`env_ids=None`（全体 env） |
| `reset` | 每次 `_reset_idx(env_ids)` | `ManagerBasedRLEnv._reset_idx` | 每回合重置时 |
| `interval` | 每步按时间计数触发 | `EventManager.apply("interval", dt=...)` in `step()` | 每步 |

**重要推论：**
- `physics_material`（摩擦）、`base_com`（CoM）、`add_joint_default_pos`（关节默认位） 均为 `startup`，**在 `load_managers` 完成时写入一次，之后 episode reset 不重采**。
- **不可**通过「在某个 iteration 再触发 startup」来改变这三项，除非显式调用 `event_manager.apply("startup")` 或改成 `mode="reset"`。
- 因此这三项**不纳入课程**；课程化对象仅为：**观测噪声（每步采样）** 和 **push_robot（interval 事件）**。

## 4. 可课程化的两个维度

### 4.1 观测噪声（Obs Noise）

当前 `ObservationsCfg.PolicyCfg` 中各 `ObsTerm` 均附带 `Unoise`：

| Term | 噪声幅度 |
|------|---------|
| `motion_anchor_pos_b` | `±0.25 m` |
| `motion_anchor_ori_b` | `±0.05 rad` |
| `base_lin_vel` | `±0.5 m/s` |
| `base_ang_vel` | `±0.2 rad/s` |
| `joint_pos` | `±0.01 rad` |
| `joint_vel` | `±0.5 rad/s` |

**问题**：早期策略尚未学会跟踪参考，噪声等于在目标上又加模糊，有效信号更弱，延迟收敛。  
**课程化方案**：在 runner 中维护 `env.obs_noise_scale`（float，初始 0.2）随 iteration 线性升到 1.0，并同步写入 `ScaledUniformNoiseCfg.scale`，对原始 `[n_min, n_max]` 做连续幅度缩放。

### 4.2 Push Robot（Interval 推力事件）

当前 `push_robot` 用 `push_by_setting_velocity`，`interval_range_s=(1.0, 3.0)`，扰动范围 `VELOCITY_RANGE`（各轴 ±0.2～0.78）。

**问题**：早期策略根本没有抗扰能力，大扰动导致大量摔倒，有效样本稀疏。  
**课程化方案**：在 `env.push_velocity_scale`（float，初始 0.1）随 iteration 线性升到 1.0，自定义 `curriculum_push_by_setting_velocity` 基于该值缩放速度范围。

### 4.3 强度课程（连续斜坡）vs 硬开关

| 方式 | 与 Isaac Lab 契合度 | 训练稳定性 | 推荐 |
|------|-------------------|-----------|------|
| 强度斜坡（标量 × 幅度） | ✅ 事件始终注册，只改幅度 | ✅ 分布连续变化 | **推荐** |
| 硬开关（改 mode / noise=0） | ⚠️ 需改 ObsGroup 内部标志或 Cfg | ❌ 切换时分布突变 | 不推荐 |

## 5. 自适应早停

**设计**：在 `FastMotionOnPolicyRunner.log()` 中（继承自 `MotionOnPolicyRunner` 的训练循环）：
- 维护长度为 `plateau_window`（默认 1000 iter）的滑动窗口，记录每 iter 的 `mean(rewbuffer)`。
- 计算窗口内线性回归斜率 \(\beta\)；当 \(|\beta| < \text{plateau\_threshold}\)（默认 `5e-5`）且当前 iter \(\ge \text{min\_iterations}\) 时，保存 checkpoint 并抛出 `_EarlyStop` 结束训练。
- **仅 `Tracking-Fast-EarlyStop-G1-v0`** 将 `min_iterations` 设为 `5000` 以启用早停；**`Tracking-Fast-Full-G1-v0` 默认 `min_iterations=int(1e9)`，不启用早停**（避免误判 plateau 导致未充分训练即退出）。
- 指标来源：WandB 等与 RSL-RL 一致的 `Train/mean_reward` 日志；实现侧从 `locs["rewbuffer"]` 取量（键名随 rsl_rl 版本可能为 `rew_buffer`，需与运行环境核对）。

## 6. 200 N 站立辅助力（M4，待评估）

- **意图**：BeyondMimic 追踪的部分动作（高难度 dance / jump）的早期阶段，机器人倾向倒地；在前 3000 iter 施加竖直向上 200 N 的衰减辅助力，帮助策略在站立姿态附近探索。
- **问题**：`push_by_setting_velocity` 是速度扰动，不是力；需要新增基于 `apply_external_forces_and_torques`（Isaac Lab PhysX API）的 `EventTerm`。
- **风险**：辅助力过强 → 训练期分布偏离真实物理 → 关力后性能回落（distribution shift）；需严格控制衰减曲线并在 M1-M3 验证后再评估是否有必要。
- **结论**：M0-M3 完成后，依据 walk 与 dance 基线对比再决定是否实施 M4。

## 7. 基线 Run（用于对比）

来源：`g1_lafan1_motion_tracking.json`（WandB project `liuming-valen-qiu-the-hong-kong-polytechnic-university/g1_lafan1_motion_tracking`），固定种子 `20260506` 各随机抽一条 finished run：

| 类型 | Run 名 | Run ID | WandB 链接 |
|------|--------|--------|------------|
| Walk | `2026-03-31_12-42-09_walk2_subject4` | `bjkq41o7` | [链接](https://wandb.ai/liuming-valen-qiu-the-hong-kong-polytechnic-university/g1_lafan1_motion_tracking/runs/bjkq41o7) |
| Dance | `2026-04-09_03-08-20_dance2_subject5` | `l7c649v5` | [链接](https://wandb.ai/liuming-valen-qiu-the-hong-kong-polytechnic-university/g1_lafan1_motion_tracking/runs/l7c649v5) |

基线均使用 `Tracking-Flat-G1-v0`，`max_iterations=30000`，评估指标：WandB 上的 `Train/mean_reward`、`Command/error_anchor_pos`、`Command/error_body_pos`。

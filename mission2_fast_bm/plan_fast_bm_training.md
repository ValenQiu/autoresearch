# Fast BeyondMimic Training — 执行计划

> **For agentic workers:** 建议按任务分段执行；步骤可用 checkbox（`- [ ]`）跟踪。  
> **文档状态（2026-05-07）：** 本文件曾从工作区磁盘丢失（`mission2_fast_bm/` 未纳入 git），本版为**按当前 `whole_body_tracking`（`fast_bm_training`）实现与既有约定重建**；细节实现以仓库源码为准，勿与旧版「布尔 flag + 双文件 curriculum」混淆。

**Goal:** 通过独立可训练的消融（ablation），验证「课程观测噪声 / 课程 Push / 自适应早停」对收敛与算力的影响；**不修改** `Tracking-Flat-G1-v0`。目标仍为：在保质量前提下，显著缩短达到基线水平所需迭代或 wall-clock（计划目标：≤21000 iter 达基线 plateau 的 90%，见全局验收表）。

**Architecture（MimicKit-inspired，无布尔 flag）：**

- **共享 `G1FastEnvCfg(G1FlatEnvCfg)`**：`ScaledUniformNoiseCfg` + `curriculum_push_by_setting_velocity`；默认与 Flat 等价。
- **共享 `FastMotionOnPolicyRunner(MotionOnPolicyRunner)`**：只重写 `log()` / `learn()`；行为由 **哨兵超参** 驱动（如 `noise_scale_start=1.0` 表示噪声课程关闭，`min_iterations=int(1e9)` 表示早停关闭）。
- **每个消融一个 task + runner cfg 子类**，仅覆盖需要激活的哨兵字段。

**Tech Stack:** Isaac Lab v2.1.0 · RSL-RL · `whole_body_tracking`（`fast_bm_training`）· PyTorch · WandB

---

## Task ID 一览

| Task ID | 功能 | runner cfg |
|---------|------|------------|
| `Tracking-Fast-G1-v0` | M0：与 Flat 等价（基线复现） | `G1FastBasePPORunnerCfg`（哨兵全关） |
| `Tracking-Fast-Noise-G1-v0` | M1：仅课程观测噪声 | `G1FastNoisePPORunnerCfg` |
| `Tracking-Fast-Push-G1-v0` | M2：仅课程 Push | `G1FastPushPPORunnerCfg` |
| `Tracking-Fast-EarlyStop-G1-v0` | M3：仅自适应早停 | `G1FastEarlyStopPPORunnerCfg` |
| `Tracking-Fast-Full-G1-v0` | M_Full：噪声 + Push（**默认关闭早停**） | `G1FastFullPPORunnerCfg` |

启训示例：

```bash
python scripts/rsl_rl/train_fast.py --task=Tracking-Fast-Noise-G1-v0 \
    --registry_name=<your-org>/wandb-registry-motions/walk2_subject4 ...
```

---

## 课程/早停公式速查（iteration = $n$）

> **预览说明**：使用 `$$ … $$`（块公式）与 `$ … $`（行内公式）。若编辑器不渲染，请启用 Markdown Math（如 `markdown.math.enabled`）。

### 1) 统一线性课程函数

$$
s(n; \text{start}, T)=
\begin{cases}
1, & T \le 0 \ \text{or}\ \text{start}=1 \\
\min\left(1,\ \text{start} + (1-\text{start})\frac{n}{T}\right), & \text{otherwise}
\end{cases}
$$

- `start=1.0` 为哨兵值，表示该课程关闭。

### 2) 观测噪声课程

$$
s_{\text{noise}}(n)=s(n; s_{n0}, T_n)
$$

对任意噪声项原始范围 $[a,b]$，第 $n$ 轮有效范围：

$$
[a_n,b_n]=[a\cdot s_{\text{noise}}(n),\ b\cdot s_{\text{noise}}(n)]
$$

**M_Full（噪声）**：$s_{n0}=0.2,\ T_n=5000$。

### 3) Push 课程

$$
s_{\text{push}}(n)=s(n; s_{p0}, T_p)
$$

对任意 push 速度轴原始范围 $[v_{\min},v_{\max}]$，第 $n$ 轮有效范围：

$$
[v_{\min}(n),v_{\max}(n)] =
[v_{\min}\cdot s_{\text{push}}(n),\ v_{\max}\cdot s_{\text{push}}(n)]
$$

**M_Full（Push）**：$s_{p0}=0.1,\ T_p=8000$。

### 4) 自适应早停

记窗口长度 $W=\text{plateau\_window}$，阈值 $\tau=\text{plateau\_threshold}$，最早触发轮次 $n_{\min}=\text{min\_iterations}$。

当 $n \ge n_{\min}$ 且窗口样本已满时，计算窗口奖励线性回归斜率：

$$
\beta_n =
\frac{\sum_{i=0}^{W-1}(i-\bar i)(r_{n-W+1+i}-\bar r)}
{\sum_{i=0}^{W-1}(i-\bar i)^2},
\quad
\bar i=\frac{W-1}{2}
$$

触发早停条件：

$$
|\beta_n| < \tau
$$

**Runner 默认超参**：$W=1000,\ \tau=5\times10^{-5}$。**仅 M3**（`Tracking-Fast-EarlyStop-G1-v0`）设 $n_{\min}=5000$ 使上式生效；**M_Full** 使用 `min_iterations` 哨兵，**默认不启用早停**。

---

## 文件变更总览（相对 `whole_body_tracking/`）

| 操作 | 路径 | 职责 |
|------|------|------|
| **新建** | `source/.../tasks/tracking/mdp/curriculum.py` | `ScaledUniformNoiseCfg`、`curriculum_push_by_setting_velocity`（单文件） |
| **新建** | `source/.../tasks/tracking/config/g1/fast_env_cfg.py` | `G1FastEnvCfg` |
| **新建** | `source/.../tasks/tracking/config/g1/agents/rsl_rl_fast_ppo_cfg.py` | `G1FastBasePPORunnerCfg` + 消融子类 + `G1FastFullPPORunnerCfg` |
| **新建** | `source/.../utils/fast_on_policy_runner.py` | `FastMotionOnPolicyRunner` |
| **修改** | `source/.../tasks/tracking/config/g1/__init__.py` | 注册 5 个 Fast task |
| **修改** | `source/.../tasks/tracking/mdp/__init__.py` | 导出 `curriculum` |
| **新建** | `scripts/rsl_rl/train_fast.py` | patch `train` 模块内 `OnPolicyRunner` 后调 `main()` |
| **新建** | `scripts/rsl_rl/selftest_fast.py` | 无仿真逻辑自测 |
| **可选** | `source/.../utils/wandb_bootstrap.py`、`train.py` 预检 | WandB 版本与 key（按你分支实际为准） |

**不修改（约定）：** `flat_env_cfg.py`、`tracking_env_cfg.py`、`rsl_rl_ppo_cfg.py` 中 Flat 默认训练配置保持不动（Fast 走独立 task）。

### 实现注记（与仓库对齐时请核对）

- `train_fast.py` 必须 patch **`import train as _train_mod` 后的 `_train_mod.OnPolicyRunner`**，而非仅改 `my_on_policy_runner` 模块属性。
- **已知问题（待修）：** Isaac Lab `ObservationManager` 调用 `term_cfg.noise.func(obs, term_cfg.noise)`（第二个参数为 **noise cfg**，不是 `env`）。若 `ScaledUniformNoiseCfg.__call__` 仍从「伪 env」读 `obs_noise_scale`，则**噪声课程在运行时可能不生效**；修复后需重跑 M1 / M_Full 消融。
- `G1FastFullPPORunnerCfg`：**不覆盖** `min_iterations`，继承基类 `int(1e9)`，早停默认关闭。

---

## M0：基础设施

**目标：** 5 个 task 可注册、可导入；`Tracking-Fast-G1-v0` 与 Flat 行为对齐（哨兵全关）。

**验收：**

- `python scripts/rsl_rl/selftest_fast.py` 在当前环境通过（脚本内约 **25** 条 `r.check`，以控制台汇总为准）。
- 任选 `--task=Tracking-Fast-G1-v0 --max_iterations=1` 冒烟启训。

**实现任务（检查清单，非粘贴全代码）：**

- [ ] `mdp/curriculum.py`：`ScaledUniformNoiseCfg`（建议与 `UniformNoiseCfg` + `curriculum_uniform_noise` 对齐 Hydra）、`curriculum_push_by_setting_velocity`
- [ ] `fast_env_cfg.py`：替换 policy 噪声与 `push_robot` event
- [ ] `rsl_rl_fast_ppo_cfg.py`：基类 + 4 消融 + Full（哨兵）
- [ ] `fast_on_policy_runner.py`：`_linear_schedule`、`_update_curriculum`、`_check_plateau`、`log` / `learn`
- [ ] `g1/__init__.py`：`_FAST_TASKS` 注册
- [ ] `train_fast.py`、`selftest_fast.py`

---

## M1 ~ M_Full：独立训练实验

在 M0 通过后，主要通过 **换 `--task`** 做消融；无需改代码即可跑 M1/M2/M3/M_Full。

**控制变量：** 同一 `registry_name`（同一 motion artifact），`num_envs`、`max_iterations`、种子策略一致，便于对比。

**WandB：** 关注 `Train/mean_reward`、`Train/obs_noise_scale`、`Train/push_velocity_scale`、`Perf/collection time`。

---

## M4（可选）：站立辅助力

见 `README.md` 背景节；**仅在 M1–M3 收益不足时再评估**。实现需新 `EventTerm`（力而非速度），并建议同样用**哨兵**（如 `assist_scale_start=0` 表示关）而非布尔 flag。

---

## M_Cleanup：收敛为单一对外 Task（未执行则仍为计划）

**目标：** 仅保留一个 Fast task（如仍名 `Tracking-Fast-G1-v0`），runner cfg 命名与 `G1FlatPPORunnerCfg` 对称（例如将 `G1FastFullPPORunnerCfg` **重命名**为 `G1FastPPORunnerCfg`）；归档或删除消融专用 cfg 类与多余注册。

**验收（草案）：**

- `selftest_fast.py` 用例与 PASS 数更新并文档化。
- `grep` 无 `enable_noise` 等遗留布尔开关（当前架构本不应存在）。
- `train_fast.py --task=Tracking-Fast-G1-v0` 为唯一推荐入口。

---

## 全局验收标准（Mission 2 完成）

| # | 阶段 | 指标 | 标准 |
|---|------|------|------|
| 1 | M0 | `selftest_fast.py` | 以当前脚本输出 PASS 总数为准（重建时约 25 条 `r.check`） |
| 2 | M1 | Walk 消融 vs 基线 `bjkq41o7` | `Tracking-Fast-Noise-G1-v0` 在 ≤ 21000 iter 达基线 plateau reward 的 90%（**噪声课程接线修复后**重跑验收） |
| 3 | M1 | Dance 消融 vs 基线 `l7c649v5` | 同上 |
| 4 | M2 | Walk / Dance Push 消融 | 同 iter / 90% 标准 |
| 5 | M3 | 早停消融（**仅** `Tracking-Fast-EarlyStop-G1-v0`） | 记录触发 iter 与 reward；推荐触发或后续 checkpoint ≥ 基线 90%；若仅验证「可提前结束」须在报告中说明 |
| 6 | M_Full | Walk / Dance | **不与 M3 绑定**；不要求早停。≤21000 iter（或商定上限）终局 ≥ 基线 90%；WandB 中 `Train/obs_noise_scale`、`Train/push_velocity_scale` 符合 schedule（**噪声修复后**） |
| 7 | M_Cleanup | `selftest_fast.py` | Cleanup 完成后更新用例数与通过标准 |
| 8 | M_Cleanup | 残留检查 | 无计划外的 feature flag / 多余 task |
| 9 | M_Cleanup | 启训 | `train_fast.py --task=Tracking-Fast-G1-v0` 正常 |
| 10 | 全程 | Flat 完整性 | `Tracking-Flat-G1-v0` 及 Flat 配置未被改坏 |
| 11 | 全程 | selftest 时长 | 全量 headless 自测在约定时间内完成（如 ≤30s，视机器调整） |

**说明：** `G1FastFullPPORunnerCfg` 默认 **`min_iterations=int(1e9)`**，早停关闭；M3 与 M_Full 验收分列。

---

## 常见坑与注意事项

| 坑 | 说明 |
|----|------|
| `train_fast.py` patch 位置 | 必须 patch `train` 模块内已绑定的 `OnPolicyRunner` 名 |
| `rewbuffer` 键名 | RSL-RL 版本可能为 `rewbuffer` 或 `rew_buffer` |
| 噪声 `func` 签名 | 须与 Isaac Lab `observation_manager` 一致：`func(obs, noise_cfg)` |
| `MotionOnPolicyRunner.learn` 的 `finally` | 早停异常路径下仍需保证 `wandb` 等清理逻辑可接受 |
| `startup` 事件 | 摩擦 / CoM / 关节 default 不纳入迭代课程 |
| 消融控制变量 | 同一 `registry_name`（同一 clip） |

---

## 不在 Mission 2 范围（后续 Mission）

Teacher–Student 蒸馏、简化碰撞预训练等见 [`research/research_teacher_student_pretrain.md`](research/research_teacher_student_pretrain.md)。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-07 | 磁盘丢失后重建；对齐哨兵架构、Full 默认无早停、公式块、全局验收表与已知噪声接线问题 |

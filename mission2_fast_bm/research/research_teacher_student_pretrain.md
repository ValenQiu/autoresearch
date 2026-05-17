# 调研：理想仿真预训练（Teacher）与部署向 Student 蒸馏

> **状态**：调研归档，供后续独立 Mission 使用。  
> **与 Mission 2 关系**：Mission 2（Fast BM）聚焦课程化噪声/Push 与训练管线工程化；**本文件所述 Teacher–Student 与碰撞简化预训练不在 Mission 2 交付范围内**，仅作技术储备与路线对齐。

---

## 1. 问题背景

### 1.1 动机

- **训练加速**可通过两类杠杆：
  - **算法/课程**：在固定物理保真度下提高样本效率（Mission 2 主战场）。
  - **环境近似**：降低单步仿真成本（如简化碰撞几何、减弱部分接触），缩短 wall-clock，但会改变动力学与接触统计。

### 1.2 与真机部署的张力

- 简化碰撞会改变 **接触流形、自碰、地面交互**，进而影响 `undesired_contacts`、终止条件与摔倒恢复分布。
- **直接**用「强简化碰撞」训练得到的策略作为**最终**部署策略，**sim2real 风险较高**。
- 更稳妥的叙事是：**Teacher 在理想/轻碰撞域快速学先验；Student 在高保真域对齐部署观测与物理**，必要时再 RL 微调。

---

## 2. 方案谱系（由简到繁）

### 2.1 两阶段离线蒸馏（推荐作为首版工程路径）

| 阶段 | 环境 | 观测 | 目标 |
|------|------|------|------|
| Teacher RL | 可简化碰撞、可 privileged | 全观测或 critic 组 | 高质量动作与跟踪先验 |
| Student 蒸馏 | **高保真碰撞**、部署一致 | 仅 policy/机载可用项 | 模仿 Teacher 动作（+ 可选 value/latent） |
| Student 微调 | 同蒸馏 | 同蒸馏 | 小步长 PPO，修补分布偏移 |

**损失（常见组合）**

- **行为克隆**：\(\mathcal{L}_{\mathrm{BC}} = \| \pi_s(o_s) - a_t \|^2\) 或对高斯策略用 KL。
- **辅助**：预测 Teacher 隐变量 / 特权量（RMA 类）；或对 critic 做 value distillation（视框架而定）。

**优点**：实现边界清晰、易做对照实验。  
**缺点**：若 Teacher 状态分布与 Student 差异大，需 DAgger 或延长微调。

### 2.2 在线 DAgger / 并行 Teacher–Student（CTS）

- 在 Student 实际遇到的 `(o_s)` 上请求 Teacher 标签，缓解 **covariate shift**。
- 工程复杂度高于纯离线蒸馏，适合作为第二阶段优化。

### 2.3 与「碰撞简化」的绑定方式

- **Teacher-only**：仅 Teacher 使用简化碰撞；Student 训练与评估始终高保真。
- **课程式**：Teacher 从简到繁碰撞 schedule（需额外 Mission 设计资产与配置版本矩阵）。

---

## 3. 与当前 BeyondMimic / Isaac Lab 栈的对接点

### 3.1 观测分组（现有代码）

- `whole_body_tracking` 已区分 **Policy** 与 **Privileged（critic）** 观测组（`tracking_env_cfg.py`）。
- Teacher 可自然使用 **privileged 组** 或扩展项；Student 仅用 **policy 组**（与 ONNX 部署对齐）。

### 3.2 Isaac Lab / RSL-RL 蒸馏配置

- Isaac Lab 提供 **RSL-RL Distillation** 相关配置类（示例路径，以你 checkout 为准）：
  - `source/isaaclab_rl/isaaclab_rl/rsl_rl/distillation_cfg.py`（`RslRlDistillationAlgorithmCfg`、`StudentTeacher` 等）
- 上游 **rsl_rl** 含 `Distillation` 算法实现（可参考 leggedrobotics 仓库中的 `distillation.py`）。
- Isaac Lab 社区有 **Student–Teacher 蒸馏示例 PR**（如 ANYmal 行走蒸馏），可作为脚本与 Hydra 入口的模板。

### 3.3 资产与碰撞

- G1 使用 `unitree_description` URDF；碰撞体数量与分布已在 Mission 2 旁路分析中量化（约 29 个 collision shape、14 个带碰撞 link）。
- Teacher 侧若改碰撞，建议 **独立 URDF 变体或生成后 USD**，与 Flat/Fast 任务通过 **不同 `ArticulationCfg` / task** 切换，避免污染默认部署配置。

---

## 4. 开源参考（可直接打开仓库）

以下链接便于后续 Mission 选型与代码阅读（**不构成选型承诺**，需按许可证与维护状态二次筛选）。

| 方向 | 仓库 / 资源 | 备注 |
|------|-------------|------|
| Isaac Lab 本体 | [isaac-sim/IsaacLab](https://github.com/isaac-sim/IsaacLab) | 官方 distillation cfg；与 Sim 版本绑定 |
| RSL-RL | [leggedrobotics/rsl_rl](https://github.com/leggedrobotics/rsl_rl) | `Distillation` 算法类 |
| IsaacLab 感知腿足蒸馏示例 | [linchangyi1/LocoTouch](https://github.com/linchangyi1/LocoTouch) | Teacher–student、多种监督方式 |
| RMA / privileged 经典参考 | [pmanoonpong/MITrapidmotoradaptation](https://github.com/pmanoonpong/MITrapidmotoradaptation) | Isaac Gym 时代；思想仍适用 |
| 腿足基座 | [leggedrobotics/legged_gym](https://github.com/leggedrobotics/legged_gym) | 工程习惯与 sim2real 组件参考 |
| 通用 RL 蒸馏（栈不同） | [spiglerg/sb3_distill](https://github.com/spiglerg/sb3_distill)、[dion-jy/policy-distillation-baselines](https://github.com/dion-jy/policy-distillation-baselines) | 损失与训练循环可参考，需自行对接 Isaac |

**检索关键词（后续可自行更新）**：`Isaac Lab distillation RslRlDistillation`、`privileged teacher student humanoid`、`RMA rapid motor adaptation`、`policy distillation continuous control`。

---

## 5. 建议的后续 Mission 验收指标（草案）

在实施阶段应至少包含：

1. **性能**：同等 `mean_reward` / 任务指标下 **迭代数或 wall-clock** 相对「全程高保真」基线的提升。
2. **不退化**：Student 在 **高保真** 下的终局指标 ≥ Teacher 在 **高保真** 上 finetune 后的约定阈值（或 ≥ 纯 Student from scratch）。
3. **部署一致性**：Student 观测维度、归一化与导出的 ONNX 与真机管线一致；必要时与 Mission 1 sim2real 清单对齐。
4. **鲁棒**：Push、摩擦随机、`undesired_contacts` 统计不出现灾难性回归。

---

## 6. 风险与边界

- **分布偏移**：Teacher 在轻碰撞上学到的接触策略，Student 在高保真上可能需较长微调。
- **奖励与终止**：碰撞改变会同时改变奖励与 termination 频率，对比实验需固定随机种子与任务 ID。
- **工程维护**：双资产（Teacher URDF vs Deploy URDF）需要版本管理与 CI 自检，避免混用。

---

## 7. Mission 2 收尾时的引用方式

- 在 Mission 2 的 README / 计划中仅保留 **本文件路径** 与一句「后续 Mission 实现」，避免 Mission 2 scope creep。
- 实作 Teacher–Student 时建议 **新开 mission 目录**（例如 `missionN_teacher_student_deploy/`），从本调研单拆出：任务注册、训练脚本、蒸馏配置、资产变体与评估矩阵。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-07 | 初版：理想仿真预训练 + Student 蒸馏路线、开源索引、与 Mission 2 边界声明 |

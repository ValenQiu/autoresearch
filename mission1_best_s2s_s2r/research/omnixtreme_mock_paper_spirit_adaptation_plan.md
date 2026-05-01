# OmniXtreme：按论文精神对 mock 部署做工程适配 — 审查结论与实现计划

> **论文对齐口径**：[arXiv:2602.23843](https://arxiv.org/abs/2602.23843) 中可在 **不开源训练栈** 前提下复现的「精神」包括：  
> （1）**部署侧**观测与执行链路与参考一致；（2）**推理侧**显式建模 **动作延迟 / 观测噪声** 等与训练分布同族的扰动；（3）**双策略** base+residual 的语义不被框架层「善意」破坏；（4）**物理与控制节拍**与训练基座单一真相源一致。  
> **不在 mock 内合理承诺的部分**：训练期 **PPO 残差、功率惩罚、激进 DR 全表** 的重新优化（需训练仓库）；**TensorRT 一体化 ~10 ms**（属真机栈，mock 用 ORT/CPU/GPU 即可）。

---

## 1. 可行性结论

**可以**：在 **不重新训练模型** 的前提下，对 **UHC + UnitreeBackend + loopback bridge** 这条 mock 链路做 **工程适配**，使闭环在统计意义上 **更接近论文与官方 `deploy_mujoco.py` 所假设的扰动与语义**，从而验证「摔倒来自 OOD / 执行链分叉」而非「DDS 不可救药」。

**边界**：若根因是 **切入分布**（BFM recovery → task 与 native motion frame 0）与 **策略权重复合**（residual_gain、slew、guard）的长期 OOD，则 mock 适配可能 **缓解但无法保证** 通过 `fallAndGetUp` 全段；最终仍可能需要 **训练侧 latency/状态随机化** 或 **切入帧/全身对齐** 策略级改动。

---

## 2. 严格审查：当前 mock 链路中的 Omni 实现方式

以下审查基于仓库内已冻结的工程事实：`omnixrtreme_uhc_adaptation.md`、`omnixrtreme_loopback_deployment_distilled.md`、`omni_vs_asap_bm_uhc_deployment_report.md`、`sim2real_latency_analysis.md`、`m3_p2_alignment_matrix.md`（C.5.x）。**若 UHC 子仓库版本漂移，以 `uhc/policies/omnixrtreme.py` 与对应 profile YAML 为准复核。**

### 2.1 端到端拓扑（mock）

```
PolicyRunner(50Hz) ──LowCmd──► UnitreeBackend(DDS pub)
                                    │
                    cyclonedds(lo)  │
                                    ▼
              run_g1_bridge: _on_lowcmd → stash cmd
                                    │
              sim_thread(1/simulate_dt, Omni 常为 250Hz) → mj_step → PD+摩擦 → snapshot
                                    │
              PublishLowState (inline, patched) ──► DDS
                                    │
PolicyRunner._on_lowstate ◄───────────────────────
         │
         └──► OmniXtremePolicy: real_obs / history / command_obs / FK / envelope / ...
```

**审查结论（链路级）**：

| 节点 | 行为 | 与论文 / native 的关系 | 风险 |
|------|------|------------------------|------|
| **Round-trip 延迟** | 实测 cmd→state **~13 ms 均值**，尖峰更高；GIL + Python DDS 序列化 | 论文后训练 Table I：**动作延迟 [5,10] ms**（更紧）；预训练 [0,15] ms。mock **均值落在预训练区间**，但 **jitter 谱与 Isaac 训练不完全同构** | 高动态对 **一步观测滞后** 敏感；Omni **历史 FIFO** 会累积误差 |
| **状态源** | LowState 来自 bridge 快照（qpos/qvel/IMU sensor patch） | 论文真机：**骨盆 IMU + FK**；native sim：**MuJoCo 真值** | mock 在 **patch 正确** 时接近 native；若 IMU 命名/offset 错则 **command_obs/FK 链 OOD**（C.5.7 已契约化） |
| **物理基座** | profile 驱动 `scene_xml`、`simulate_dt` | 必须与 sim2sim **同一真相源**（C.5.5）；Omni 常用 **0.004 s** | 混用 0.005/默认 XML 会导致 **接触动力学分叉**（已记录根因） |
| **执行器语义** | UHC 内包络 + **每子步摩擦** | 与 `deploy_mujoco.py` 常数表对齐结论：**已逐项一致** | loopback 上 **PD 应用时机** 若与「参考单线程」有细微差，仍可能放大 |
| **策略层「稳定化」** | `residual_gain`、`q_target_slew`、`residual_guard`、`task_entry_stabilize` 等 | **native 无 slew/guard**；`RESIDUAL_GAIN` 默认 **1.0**；UHC 曾用 **0.35** + slew **6.0** | **明确偏离** native 分布；distilled 文档将 **A1–A4 单变量实验** 列为最高优先级 |
| **切入与参考** | BFM recovery + 上肢/可选下肢插值 → `MotionReferenceSource` 某 `start_frame` | native：**整机关节+root 对齐 motion 第 0 帧** | **command_obs 与机体速度/接触不一致** 时，FM  early correction 放大 → tick≈25 首发散（已观测） |
| **历史缓冲** | 15×90 FIFO，`history_warm_start` 等 | 与论文 **h** 一致；**任一步污染 → 自激** | mock 下 **延迟一步** 的 `command_obs` vs `real_obs` 对齐必须审计 |

### 2.2 OmniXtremePolicy 内部（逻辑审查摘要）

- **双 ONNX + 可选 FK**：与论文 **base + residual** 一致；residual 输入需 **含 base 动作**（与 III-B1 一致）。  
- **`initial_noise`**：若导出非零输入，mock 必须与 sim2sim **同分布**（全零 = OOD）。  
- **`skip_position_clip`**：框架级 URDF 裁剪会破坏高动态（已复盘）；mock **必须保持 true**。  
- **UHC-only 旋钮**：`residual_gain`、`q_target_slew_rate`、`residual_guard`、`entry_align`、`pre_settle_ticks` — 属于 **工程补偿**，不是论文章节；**与 native 对齐时应优先收敛到「默认关闭或等于 env」** 再谈论文 DR。

### 2.3 审查总判

1. **延迟**：mock **不是**「比论文差一个数量级」的单一 bug；但 **未显式注入与 Table I 一致的随机延迟/子步对齐** 时，**无法声称已复现论文后训练环境**。  
2. **首发散**：文档指向 **native 与 UHC 的策略输出路径差异**（gain/slew/guard/切入态）优先于继续改 bridge。  
3. **物理与传感器**：在 C.5.x 契约满足后，**不应再默认怀疑 bridge IMU/motor patch**，除非观测对比脚本显示分叉。

---

## 3. 论文精神 → mock 可落地的映射表

| 论文元素 | mock 工程对应 | 备注 |
|----------|---------------|------|
| 动作延迟 [0,15] / 后训 [5,10] ms | bridge 或 PolicyRunner 侧 **可复现随机延迟 buffer**（按控制步或按物理子步调度），配置区间对齐 Table I | `deploy_mujoco.py` 用 `action_depaly_decimation` 在子步内随机施加；mock 可对 **LowCmd 生效时刻** 或 **policy 使用的 state 时间戳** 建模 |
| 观测噪声（Table I 各类 scale） | `config.yaml` 式 `noise_scales`：**mock 可开关**「训练式轻噪」用于 **鲁棒性 smoke**，默认关以保证与 native 字节对齐 | 与 `compare_omni_deploy_obs` **互斥模式**：对齐实验关噪，鲁棒实验开噪 |
| 残差 + 冻结 base | 已是双 ONNX；**禁止在 mock 调试阶段随意改 fusion 公式** | 仅改 gain 时走单变量矩阵 |
| 力矩–速度 + 摩擦 | UHC 已与 native 常量一致；mock 保持 **同一 profile XML + simulate_dt** | 不再作为第一怀疑项 |
| IMU + FK（III-C） | mock 用 sensor patch + FK ONNX；**增加「LowState 时间戳 vs policy tick」漂移监控** | 论文真机 10 ms E2E；mock 记录 **obs 年龄** 便于对照 |

---

## 4. 实现计划（分阶段、可验收）

### 阶段 0：基线与门禁（0.5–1 天）

| 任务 | 验收 |
|------|------|
| 固定 **profile + commit**：`sim2real_g1_loopback_bfm_*.yaml` 中 Omni 段、`omnixrtreme.yaml`、bridge 启动参数写入一次 **可复现实验记录**（md 或 issue 模板） | 他人可按文档复现同一 **first divergence tick** 量级 |
| 跑通 **无改动** 一次 loopback + 保存 `audit_csv`（若已支持） | 有 tick 0/25/50 的 baseline 文件 |

### 阶段 1：native 分布对齐（论文精神：**部署语义一致**）（1–2 天）

**原则**：每次只改 **一个** 旋钮（见 `omnixrtreme_loopback_deployment_distilled.md` §5–6）。

| 顺序 | 任务 | 验收 |
|------|------|------|
| A1 | `residual_gain: 1.0`（对齐 `RESIDUAL_GAIN` 默认） | first divergence tick **≥** baseline 或 qerr_top5 改善 |
| A2 | `q_target_slew_rate_rad_s: 0`（关闭 slew） | 同上 |
| A3 | `residual_guard_enabled: false`（仅诊断用） | 确认 guard 非第一根因后可恢复或改为更晚介入 |
| A4 | A1+A2+A3 组合 | 与 **同 motion** 下 native `deploy_mujoco.py` 的 **raw/base/res** 范数曲线定性可比 |

**产出**：更新 `omnixrtreme.yaml` 的 **「诊断 profile」与「保守运行 profile」** 分离（或 `omnixrtreme.native_align.yaml` overlay），避免默认把生产式 guard 关掉。

### 阶段 2：论文 Table I 式 **mock 侧扰动注入**（工程逼近后训练环境）（2–4 天）

| 任务 | 说明 | 验收 |
|------|------|------|
| B1 | 实现 **动作延迟模块**：在 `simulate_dt` 子步语义下，随机延迟 **0–15 ms**（预训练）与可选 **5–10 ms**（后训）两档配置；与 `deploy_mujoco` 的 decimation 内随机对齐 **或** 在 PolicyRunner 对 `q_target` 生效时间对齐 | 延迟分布直方图可打印；关闭时与阶段 1 bit-exact（除时间戳外） |
| B2 | **观测噪声** 可选路径：仅在 `paper_randomization: true` 时注入 Table I 中与 deploy 一致的噪声项；默认 false | `compare_omni_deploy_obs` 在 false 时仍 PASS |
| B3 | **obs 年龄 / step 对齐** 日志：记录用于本步 `command_obs` 的 motion 帧索引与 `episode_length_buf` 是否一致 | 可检测「DDS 一步偏帧」类 bug |

### 阶段 3：切入分布（论文精神：**可恢复初态**）（3–5 天，与策略/产品取舍绑定）

| 任务 | 验收 |
|------|------|
| C1 | 定义 **`native_entry` 模式**（可选）：进入 TASK 前 **短时**将 root+qpos 拉到 motion frame 0（或对齐帧），再交给 policy；与当前「仅上肢插值」做 A/B | fall 段 tick 25 指标改善或无副作用记录 |
| C2 | `entry_align` / `_entry_start_frame` 与 `freeze_at_frame` 的 **组合表** 文档化，避免多机制同时改 | 单一真相源表格 |

### 阶段 4：自动化与 selftest 对齐（持续）

| 任务 | 验收 |
|------|------|
| D1 | 扩展或封装 `scripts/compare_omni_deploy_obs.py`：**同一 tick** 对比 native CSV vs loopback CSV（distilled 已描述方向） | CI 或 `scripts/selftest.py` 子目标可 headless 跑 **短程**（不要求全长 fall） |
| D2 | 在 `DEVELOPMENT_RULES.md` / skill 中增加一条：**Omni mock 改动必须附 native-align 与 delay-off 两套日志** | 审查可执行 |

---

## 5. 依赖与前置

- **UHC 源码树**：本 autoresearch 工作区可能 **未挂载** `universal_humanoid_controller`；实施前需 **clone/submodule** 到可编辑路径，所有改动以该仓库 PR 为单位。  
- **本地 OmniXtreme**：`/home/qiulm/sources/OmniXtreme` 作为 **golden**；任何 mock 行为改变需说明与 `deploy_mujoco.py` 哪一段对齐。  
- **真机**：本计划 **不阻塞** mock；阶段 2 的延迟注入 **反而**为真机 DDS 做分布压测。

---

## 6. 风险与不做清单

- **不要**在未完成阶段 1 前开阶段 2 的全量噪声，否则 **无法判断** 是 OOD 还是随机化本身导致失败。  
- **不要**同时调整 residual_gain、slew、guard、entry_align、延迟注入；distilled 文档中的 **单变量矩阵** 是强制纪律。  
- **不要**假设「再降 3 ms Python DDS」能替代分布对齐（`sim2real_latency_analysis.md` 已结论化）。

---

## 7. 文档与索引

- 本计划：**本文档**  
- 对照论文与公开仓库：`omnixtreme_arxiv2602_23843_paper_and_deploy_comparison.md`  
- 首发散 debug：`omnixrtreme_loopback_deployment_distilled.md`  
- 机制层对照：`omni_vs_asap_bm_uhc_deployment_report.md` §2.3–3  
- Latency：`sim2real_latency_analysis.md`

| 日期 | 修订 |
|------|------|
| 2026-05-01 | 初版：基于 mission 已沉淀文档的 mock 链路审查 + 分阶段实现计划。 |

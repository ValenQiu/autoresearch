# M3-R 执行计划：Sim2Real 推倒重来（全新实现路径）

**Milestone**: M3-R（对应 `M3.R0 ~ M3.R5`）  
**范围**: UHC -> unitree_sdk -> mujoco（loopback）到真机最小切换  
**分支策略**: 从 `02e7e79e4b8d9a315dbb6c888af8774da54f1d0a` 新建 `sim2real_debug`  
**保留策略**: `29efe68` + 一条依赖修复补丁提交（工具基线）  
**核心约束**: 不复用旧实现细节；实现阶段 `unitree_sdk -> mujoco` 与 ASAP 语义对齐  
**状态**: planning（待审核后执行）

---

## 0. 重建原则（强制）

1. **实现重建，不是补丁修复**：旧链路只作为风险对照，不作为实现模板。
2. **先证据后改动**：每次实现前先做边界输入/输出采样与语义对照。
3. **ASAP 语义对齐优先于“看起来能跑”**：控制时序、字段语义、freshness 必须一致。
4. **验收双轨制**：
   - 功能验收：看新实现是否达标；
   - 风险验收：看新旧差异是否引入灾难性行为变化。

## 0.1 Teacher 参考（RoboJuDo）与规划升级（新增）

> 参考仓库：`https://github.com/HansZ8/RoboJuDo`  
> 蒸馏文档：`mission1_best_s2s_s2r/research/robojudo_teacher_distilled.md`

将 RoboJuDo 作为 teacher 后，M3-R 增补以下强制要求：

1. **统一适配层**：obs/action/joint-order 映射入口单点化，避免散落在 backend 与 policy 两侧。  
2. **切换管理器化**：将策略切换与插值逻辑从主循环中解耦为独立 manager（含 warmup、delay、duration）。  
3. **统一命令面**：sim2sim/sim2real/loopback-debug 使用统一 CLI 参数面，尽量只改 profile 与 interface。  
4. **可观测性内建**：freshness、frame source、cmd 序号、topic 统计作为默认输出项，不再靠临时打印。

“追赶 -> 超越”分层目标：

- **追赶目标（M3-R 内）**：对齐其模块化设计与多策略接入效率。  
- **超越目标（M4+/M5）**：建立差分验收产品化、故障注入标准化、语义契约测试体系。

## 0.2 执行进展（2026-04-23 重置）

**项目级重置决定**：原 M3 两次 attempt 均被判定不可接受（main 上的 attempt #1 接近完成但被顽固 bug 拖死；sim2real_debug 上的 attempt #2 重做后同样失败）。两条分支打 tag 归档，不参与当前开发：

- `archive/main-m3-attempt1` → `e1c664a`（M3 attempt #1，冻结）
- `archive/sim2real-debug-m3-attempt2` → `0a661b6`（M3 attempt #2，冻结）

**当前基线**：UHC 新分支 `sim2real_redo` = `02e7e79` + `b791b1c`（仅移植 wandb 预下载工具）。后续 P1/P2/P3/... 一律在 `sim2real_redo` 上**重新开始**，旧实现只作差分审查参照。

| 阶段 | 状态 | 说明 |
|------|------|------|
| P0 anchor + wandb 工具 | ✅ 已完成 | UHC `b791b1c`：`tools/wandb_model_download/download_wandb_onnx.py` 移植通过（`--dry-run` + 实跑下载 beyondmimic ONNX 12MB + onnxruntime 加载验收） |
| P1 跨仓 skill 同步 | ✅ 已完成 | UHC `.cursor/skills/`：`uhc-policy-adaptation`（更新）+ `selftest-reality-alignment`、`uhc-interpolation-debugging`、`unitree-g1-sdk-dds-mock`、`unitree-g1-documentation-distilled`、`karpathy-coding-discipline`、`autoresearch-house-rules`（新增） |
| P2 对齐矩阵（Gate A） | 🟡 骨架化 | `m3_p2_alignment_matrix.md` v0 已成型；C.1.6 / C.5.3 已从 TBD 升级为 FROZEN（实测 bridge 每 `sim_dt` 发一次，G1 默认 200 Hz / OmniXtreme 250 Hz）；签字流程待真机 SOP 收尾时一并执行 |
| P3 UnitreeBackend 最小契约 | ✅ mock 侧已完成 | `uhc/backends/unitree_backend.py` 在 `sim2real_redo` 落地；mock（`domain=1/lo`）链路在 `scripts/smoke_loco_loopback.py` 全绿；`selftest_real.py` 真机路径延后到 P5 |
| P4 loopback bridge | ✅ 已完成 | DP3 落地：`third_party/unitree_mujoco` submodule + `tools/loopback_bridge/run_g1_bridge.py` 包装；200/250 Hz per-`mj_step` PD 重算；`--profile` 自动取物理基座；`UnitreeSdk2Bridge` XML 兼容 patch（默认 G1 + OmniXtreme 双支持） |
| P5 loco / BFM 闭环 + Gate C | 🟡 loopback 全绿 / 真机延后 | 三 profile（loco / BFM+CR7 / BFM+BeyondMimic）物理底座已 PASS；真机切换 checklist 待写入 `sop_sim2sim_to_sim2real.md`；按项目约束真机动作延后 |
| P6 Gate D 差分审查 | 🚧 待开始 | 对 `archive/main-m3-attempt1` 和 `attempt2` 做形式化差分 → 决定哪些设计可挽救 |

## 0.25 当前优先级与范围说明（2026-05 更新）

**真机相关一律挂起**：`selftest_real.py` 真机契约、`sop_sim2sim_to_sim2real.md` 中「真机切换 checklist」细化、首次真机站立/短走验收、DP2 全量 FK/SE 真机闭环等，**待项目明确启动真机阶段再执行**；不在当前迭代排期内完成。

**本阶段主战场：仿真 + mock（loopback）链路完善**——目标是把 **MujocoBackend 与 `UnitreeBackend(mock)+run_g1_bridge` 与 PolicyRunner** 的语义与时序对齐到可签字、可回归，而不扩展真机网卡路径。

**OmniXtreme 策略专项**：高动态 Omni 的 mock 深挖、与论文精神的工程逼近见 `mission1_best_s2s_s2r/research/omnixtreme_mock_paper_spirit_adaptation_plan.md` 与 `omnixtreme_arxiv2602_23843_paper_and_deploy_comparison.md`；**不阻塞** M3 上表 P0–P4 已绿项；与 Omni 强绑定的排障与验收 **顺延**，优先保障 **loco / BFM+CR7 / BFM+BeyondMimic** 等非 Omni-task 的 mock 矩阵稳定。

**除 Omni 外、mock 阶段仍建议补齐的文档与门禁（真机可不执行）**：

| 项 | 动作 | 说明 |
|----|------|------|
| **Gate A** | 推进 `m3_p2_alignment_matrix.md`：loopback 已实证行保持 FROZEN；真机列可标 `DEFERRED` 直至真机阶段，避免无限期 TBD | 签字可与「mock 段无 TBD」子集先行 |
| **Gate A+** | 在矩阵或附录中冻结 quat / joint order / `RobotCmd` 字段语义，并加 RoboJuDo 对照备注 | 不连硬件也可写 |
| **P5 文档** | `sop_sim2sim_to_sim2real.md` 仅补充 **mock 预检与 loopback 与 sim2sim 差异** 小节；真机 `lo→NIC` checklist 保留占位 | 与「真机挂起」一致 |
| **P6** | 起草 `research/m3_p6_attempt_diff_audit.md`（attempt1/2 vs `sim2real_redo`） | 纯文档差分，不依赖真机 |
| **BeyondMimic** | loopback 上 **WoSE ONNX** 重训仍为中期正解；当前 `override_robot_anchor_pos` 为兜底 | 属 mock 可验证的模型资产，非 Omni |

**Research 归集**：mission 相关 research 已收至 `mission1_best_s2s_s2r/research/`（索引见同目录 `README.md`）；仓库根目录 `research/README.md` 仅作跳转说明。

## 0.3 架构决策（2026-04-23 审查后拍板）

在进入 P2 之前，基于三方参考实现（ASAP / BeyondMimic / RoboJuDo）+ 官方 `unitreerobotics/unitree_mujoco` 调研，拍板两项**全局约束**：

### DP1 · RobotCmd 契约策略 = **渐进升级（B 方案）**

**证据**：`HybridRobotics/motion_tracking_controller` C++ 源码（`MotionOnnxPolicy::forward`）确认 ONNX 输出只含 `actions + joint_pos + joint_vel + body_pos_w + body_quat_w + body_{lin,ang}_vel_w`，**无 tau_ff / 无 dq_ref**；kp/kd 由静态 yaml 配置。UHC 当前 4 类策略（loco / ASAP-mimic / BeyondMimic / OmniXtreme）下发 `(q_target, kp, kd)` 已完备。

**落地**：
- P3 升级时**保留**现有 `HardwareBackend.write_action(q_target, kp, kd)` API（不加 deprecation）
- **新增**可选 `write_cmd(RobotCmd)` 完整接口；`RobotCmd` 字段 = `q, dq, kp, kd, tau_ff, mode_pr, level_flag, seq`
- backend 实现把 `write_cmd` 作为**权威入口**；`write_action` 作为薄兼容垫片
- `RobotState` 强制新增 `tick / timestamp_ns / lin_acc`；`body_xpos / body_xquat / body_xmat` 从公共接口下沉到 `MujocoBackend.get_body_frame(name)` 扩展 API
- `BeyondMimicPolicy._compute_world_to_init` 分两路：sim 走 `get_body_frame(anchor)`，real 走 `pelvis IMU + URDF 前向运动学`（DP2 中已拍板 A 方案）

### DP3 · Loopback Bridge 实现方式 = **官方 `unitreerobotics/unitree_mujoco` submodule（E 方案，新增选项）**

**证据**：
- [`unitreerobotics/unitree_mujoco`](https://github.com/unitreerobotics/unitree_mujoco)（908⭐ 官方）提供完整的 `DDS ↔ MuJoCo` bridge，C++ / Python 双版本
- G1 需用 `unitree_hg` IDL（Go2 用 `unitree_go`），[`lerobot/unitree-g1-mujoco`](https://huggingface.co/lerobot/unitree-g1-mujoco/blob/main/sim/unitree_sdk2py_bridge.py) 已完成 G1 适配（elastic band + joystick + unitree_hg）
- 官方约定：`ChannelFactoryInitialize(1, "lo")` = sim（domain=1）；`ChannelFactoryInitialize(0, "enp2s0")` = real（domain=0）——ASAP / RoboJuDo / UHC 共用此约定
- UHC 自己写 bridge 的风险：DDS IDL 代码需维护、官方升级需跟踪、语义与真机 drift 风险

**落地**：
- `third_party/unitree_mujoco/` 作为 git submodule 引入（UHC 仓库）
- `tools/loopback_bridge/`（UHC）只负责：
  - `uhc_g1_bridge.yaml`：UHC 专用 G1 配置（选 `hg` IDL、`domain_id=1`、`interface=lo`、scene XML 指向 UHC 自己的 g1_29dof 场景）
  - `run_g1_bridge.sh`：包装脚本 `python third_party/unitree_mujoco/simulate_python/unitree_mujoco.py --config ...`
- UHC `uhc/backends/unitree_backend.py` 只做 DDS **客户端**（订阅 `rt/lowstate` / 发布 `rt/lowcmd`），**不实现 bridge server 侧**
- 故障注入 / 域随机化作为 **P4+ 或 M4** 的"超越目标"——短期不 patch bridge，用 bridge 原生功能（如果有）或 MuJoCo XML 层的 `<geom friction="...">`、`<default>` 改模型参数

### DP2 · BeyondMimic worldToInit 真机方案 = **URDF FK 近似（A 方案）**

真机用 `pelvis IMU quat + joint_pos` 做 URDF 前向运动学估计 anchor body 的世界位姿。预期在 `init` 瞬间一次性对齐，之后 tracking 靠相对量。工具链候选：`pin`（Pinocchio）/ `robot_descriptions.py` / 手搓 FK 链（29DoF 手写代价可控）。具体库在 P3.3 决定。

---

## 1. 目标

在不依赖旧 loopback 实现细节的前提下，重新构建并验收如下链路：

`UHC(UnitreeBackend) -> unitree_sdk2py DDS -> MuJoCo bridge -> unitree_sdk2py DDS -> UHC`

并保证真机切换只改 `interface/domain`，不改策略层逻辑。

## 2. 里程碑拆分（M3.R0 ~ M3.R5）

### M3.R0：基线整理与工作分支准备
- 从 `02e7e79...` 建立 `sim2real_debug`
- 迁移并修复 wandb 工具提交包（`29efe68 + fix`）
- 验收：工具脚本 `--help/--dry-run` 可运行

### M3.R1：ASAP 语义对齐规格冻结
- 冻结对齐矩阵：topic/字段/时序/freshness/映射
- 输出可执行检查单，作为实现 gate
- 验收：审查文档完成并经人工确认

### M3.R2：UnitreeBackend 深度 debug 与重构
- 先做证据采集（输入输出边界）
- 再实现最小闭环读写与可观测性
- 验收：`selftest_real.py` 契约项全通过

### M3.R3：`unitree_sdk -> mujoco` 全新 bridge 对齐实现
- 明确控制循环时序（发布状态/消费命令/步进）
- 对齐 `q/dq/kp/kd/tau` 语义
- 验收：bridge smoke + `PolicyRunner` smoke 均通过

### M3.R4：loco 闭环恢复与稳定性验收
- 在 `sim2real_g1_loco` 下完成 INIT/ACTIVATE/WALK/E_STOP
- 验收：`min_z/max_tilt`、状态机流程和人工观感通过

### M3.R5：差分验收与真机最小切换准备
- 新旧实现行为差异审查（防灾难性更新）
- 固化真机切换 checklist（`lo -> enp2s0` + domain）
- 验收：文档签字 + 自测门禁全部绿

## 3. 验收门禁（Gate）

- **Gate A（R1 结束）**：对齐矩阵完整且无 TBD
- **Gate B（R3 结束）**：`selftest_loopback_bridge_smoke.py` + `selftest_loopback_policy_runner_smoke.py` 通过
- **Gate C（R4 结束）**：`sim2real_g1_loco` 稳定通过指标门槛
- **Gate D（R5 结束）**：差分审查完成，无高危未关闭项

新增 Teacher 对齐子门禁：

- **Gate A+**：适配层边界与数据契约冻结（含 quat 约定、joint order 契约、cmd 字段语义）
- **Gate B+**：切换管理器日志可观测（含切换来源、插值阶段、延迟与 warmup 状态）
- **Gate D+**：输出“新旧行为差分报告”并关闭全部高风险项后，才允许进入真机最小切换

## 4. 与旧方案关系

- 原 `M3` 第一版计划（UnitreeBackend + loopback 细节设计）已切出为 [`.archive/main_m3/m3_original_deprecated.md`](.archive/main_m3/m3_original_deprecated.md)，仅供复盘对照，不作为实现依据。
- 同期归档：`rebuild_m3_acceptance_matrix.md`、`review_uhc_vs_mtc_loopback_alignment.md`、`runbook_loopback_uhc_mujoco.md`、`s3_s4_loopback_risks_and_checklist.md` → 全部位于 `.archive/main_m3/`。
- 新执行以本文件顶部章节为准（锚点 UHC `02e7e79`，工作分支 `sim2real_redo`）。


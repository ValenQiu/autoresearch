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
| P2 对齐矩阵（Gate A） | 🚧 待开始 | 重新冻结 ASAP 语义对齐矩阵；不复用 `rebuild_m3_acceptance_matrix.md`（已归档） |
| P3 UnitreeBackend 最小契约 | 🚧 待开始 | 按新对齐矩阵重新实现；`selftest_real.py` 重写，走 `PolicyRunner` 同路径（`selftest-reality-alignment` skill） |
| P4 loopback bridge | 🚧 待开始 | 按 `unitree-g1-sdk-dds-mock` skill 重新实现 mock bridge；先 headless smoke |
| P5 loco 闭环 + Gate C | 🚧 待开始 | `sim2real_g1_loco` 先 loopback smoke，再真机 |
| P6 Gate D 差分审查 | 🚧 待开始 | 对 archive/main-m3-attempt1 和 attempt2 做形式化差分 → 决定哪些设计可挽救 |

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


# M4.1：多策略在线切换（Plan A 透明中转）

**状态**：✅ 代码已落地（UHC `PolicyRunner`）  
**验收**：sim2sim 中「TASK_ACTIVE 下 `;` / `'` 排队切换 → 经 loco 上肢插值 → 进入下一 task」已打通；**正式「BeyondMimic→CR7→BeyondMimic 连续 5 次不倒」**建议在多 task profile 下做一次人工/录屏回归并补 selftest。

## 实现要点（与 `task_best_s2s_s2r.md` 对齐）

| 任务描述 | 实现位置 |
|----------|----------|
| `;` / `'` 在 TASK_ACTIVE 触发切换 | `PolicyRunner._switch_task_by_offset()` → 设置 `_pending_task_switch_idx`，调用 `_begin_exit_task()` |
| TASK→loco（加速）→TASK' | 退出任务时上肢插值回 loco；`exit_task` 插值结束后若 `_pending_task_switch_idx` 非空，则 `active_task_idx` 更新并 `_begin_enter_task()` |
| 机制命名 | 字段名为 `_pending_task_switch_idx`（与文档中「_pending_task_idx」同指） |

**代码**：`universal_humanoid_controller/uhc/core/policy_runner.py`（约第 60、218–231、524–542 行）。

## 待补（可选）

- [ ] 专用 profile：至少两个 `task_policies`（如 BeyondMimic + CR7/另一 mimic），用于一键复现「5 次切换」验收。
- [ ] `selftest` 或脚本：多 task 排队切换的 headless 片段（可与 DEVELOPMENT_RULES 全量策略时长要求折中）。

## 相关

- M4 总览：`task_best_s2s_s2r.md` §M4  
- OmniXtreme 与安全层：`research/omnixrtreme_uhc_adaptation.md`

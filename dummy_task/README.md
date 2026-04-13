# dummy_task 目录规范

本目录用于管理“任务级”方案文档，目标是让任务可扩展、可追踪、可交接。

## 1. 目录用途

- 存放每个任务的说明文档（人类可读）
- 存放每个任务的结构化定义（机器可读）
- 存放每个里程碑的执行计划（可执行清单）

## 2. 命名规范

每个任务至少包含两份主文件：

- `task_<task_slug>.md`
- `task_<task_slug>.json`

每个里程碑包含一份执行计划：

- `m<index>_<milestone_slug>_execution_plan.md`

示例：

- `task_humanoid_sim2x.md`
- `task_humanoid_sim2x.json`
- `m1_stand_switch_execution_plan.md`
- `m2_safety_fallback_execution_plan.md`

## 3. task_slug 规则

- 使用小写字母、数字、下划线
- 推荐长度 3-40 字符
- 建议包含任务域关键词，例如：`humanoid`、`sim2real`、`tracking`
- 禁止空格和中文字符（避免脚本处理问题）

## 4. 文件职责

- `task_<task_slug>.md`
  - 面向人类阅读
  - 包含目标、范围、架构、状态机、测试矩阵、里程碑定义

- `task_<task_slug>.json`
  - 面向脚本/代理读取
  - 包含关键字段（上下文、接口、约束、里程碑、验收标准）

- `m<index>_<milestone_slug>_execution_plan.md`
  - 单里程碑执行清单
  - 包含步骤顺序、阻塞条件、验收项、退出条件

## 5. 推荐最小字段（JSON）

建议至少包含：

- `task_name`
- `version`
- `goal`
- `project_context`
- `state_machine`
- `policy_roles`
- `backend_abstraction`
- `input_abstraction`
- `milestones`
- `test_plan`
- `deliverables`

## 6. 版本与变更规则

- `version` 使用语义化风格：`v0.1`, `v0.2`, `v1.0`
- 大改架构或状态机时，至少提升一个小版本
- 每次变更建议同步更新：
  - `task_<task_slug>.md`
  - `task_<task_slug>.json`
  - 对应 `mX_*_execution_plan.md`（若影响里程碑）

## 7. 新增任务流程

1. 新建 `task_<task_slug>.md`（写清目标与范围）
2. 新建 `task_<task_slug>.json`（写结构化配置）
3. 新建 `m1_<milestone_slug>_execution_plan.md`
4. 先对齐 M1 验收标准，再进入实现

## 8. 当前任务映射（已有）

当前目录已有任务文件命名尚为历史格式：

- `dummy_task_humanoid_sim2x.md`
- `dummy_task_humanoid_sim2x.json`

后续新增任务请优先使用本 README 的标准命名：

- `task_<task_slug>.md/json`

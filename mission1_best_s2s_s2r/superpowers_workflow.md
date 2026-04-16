# Superpowers 与本仓库工作流融合

**目的**：把 [obra/superpowers](https://github.com/obra/superpowers) 的 14 个流程型 skills 与本仓库的 **DEVELOPMENT_RULES.md**、**selftest-reality-alignment** 对齐，避免「测试全过、实跑就错」。

## 仓库内布局

| 位置 | 说明 |
|------|------|
| `third_party/superpowers/` | git submodule，上游 `obra/superpowers` 的 `main` |
| `.cursor/skills/superpowers-<name>/` | **符号链接** → `../../third_party/superpowers/skills/<name>/`，Cursor 自动发现 skill |
| `.cursor/skills/uhc-policy-adaptation/` | **本仓库自有**：UHC 新策略适配核对表（与 superpowers 独立） |

同步上游：

```bash
cd third_party/superpowers && git fetch origin && git pull --ff-only origin main
```

`.cursor/skills/` 下无需再复制一份 SKILL.md；更新 submodule 即更新 Cursor 侧可见内容。

## 14 个 Superpowers Skills（与 submodule 一一对应）

1. **using-superpowers** — 会话开始：先判断是否有适用 skill，再行动或追问  
2. **brainstorming** — 做功能/改行为前先澄清需求与设计  
3. **writing-plans** — 多步任务先写实现计划再动代码  
4. **test-driven-development** — 先测后写实现（与仓库规范一致）  
5. **systematic-debugging** — 遇 bug/测试失败先按流程根因分析  
6. **verification-before-completion** — 声称完成前必须跑过验证命令并有输出证据  
7. **executing-plans** — 已有书面计划时的分阶段执行与检查点  
8. **subagent-driven-development** — 计划拆给子任务时的协作方式  
9. **dispatching-parallel-agents** — 多路独立任务并行  
10. **using-git-worktrees** — 需要隔离分支/工作区时用 worktree  
11. **requesting-code-review** — 大改/合并前请求评审的检查清单  
12. **receiving-code-review** — 对待评审意见：核实再改，不盲从  
13. **finishing-a-development-branch** — 收尾：合并/PR/清理选项  
14. **writing-skills** — 编写或迭代 Cursor/Codex skills 时的规范  

## 与本仓库「自身能力」的优先级（融合规则）

1. **用户在本对话中的明确指令**（最高）  
2. **DEVELOPMENT_RULES.md**（自测先行、全链路对齐、策略跑满等）  
3. **`.cursor/skills/selftest-reality-alignment/SKILL.md`**（与「真实运行路径」对齐的自测设计）  
3b. **`.cursor/skills/uhc-policy-adaptation/SKILL.md`**（新 ONNX 策略接入 UHC：物理节拍、安全层 `clip_action`、与参考 deploy 对齐）  
4. **Superpowers skills**（流程与纪律：何时 brainstorm、何时 TDD、完成前验证等）  
5. 默认系统行为（最低）

若 Superpowers 某条与 `DEVELOPMENT_RULES` 冲突：**以 DEVELOPMENT_RULES 为准**（例如本仓库强制 selftest 与真实 profile 对齐）。

## Agent 执行约定（简要）

- 可能适用 skill 时：**先读对应 SKILL.md**（Cursor 内为加载 skill 内容），再回复或改代码。  
- 声称「完成 / 通过 / 可合并」：**必须先满足 verification-before-completion**（有命令与输出）。  
- 集成类改动：**满足 selftest-reality-alignment**（与 `run.py` / PolicyRunner 同路径、步进与时序一致）。  

---

*文档随 submodule 与规范更新维护。*

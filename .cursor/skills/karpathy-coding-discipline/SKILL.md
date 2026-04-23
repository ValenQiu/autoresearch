---
name: karpathy-coding-discipline
description: >-
  Karpathy-inspired coding discipline for LLM coding agents. Use before writing
  or modifying code, before creating abstractions, before "improving" adjacent
  code, and whenever about to start a multi-step task without a verifiable
  success criterion. Surfaces the four rules (Think Before Coding / Simplicity
  First / Surgical Changes / Goal-Driven Execution) as red-flag-driven
  checklists so the agent catches itself rationalizing.
---

# Karpathy Coding Discipline

## Source of truth

本 skill **即是 canonical 源**（入库 + 镜像到 UHC）。`CLAUDE.md` 在本仓库 `.gitignore` 内（launcher session 生成的本地视图），其顶部「通用行为准则」段落应视为"本 skill 的简要回显"，若冲突以本 skill 为准。

## 何时启用（强制）

对 autoresearch / UHC / 任何本机仓库的任何 coding / refactor / debug 任务，**在动手前**都应加载本 skill，除非任务只是信息性问答。

典型触发：
- 用户说「帮我实现 / 新增 / 修 / 重构 / 重写 / 接入」
- 已进入 Agent mode 准备写 diff
- 看到不相关但"顺手能改"的代码
- 计划写 >100 行代码、>5 步的操作

## 四条准则 → 四份 checklist

### 1. Think Before Coding — 不假设、不隐藏困惑、surface tradeoffs

**启动前必做**：

- [ ] 明示假设：我假设 X；如果是 Y，方案不同 → 先问一次
- [ ] 多解读：用户原话有 ≥2 种合理解读时，列出让用户选
- [ ] 简单方案：如果存在显然更简单的做法，写出来再决定
- [ ] 不清楚 = 停：命名困惑所在，优先提问

**red flag thoughts（出现即停）**：
- 「我大概猜到用户是要 Y，直接做」
- 「先做着吧，做完不对再说」
- 「我需要更多上下文」但不问用户

### 2. Simplicity First — 最小代码解决问题

**checklist**：

- [ ] 我写的每个函数 / 类 / 参数，是此次需求真的要的吗？
- [ ] 有没有为不存在的用例加"灵活性"、"可配置"？
- [ ] 有没有为不可能的场景加 error handling？
- [ ] 200 行能否压到 50？若能，压。
- [ ] 问自己：senior engineer 会说「overengineered」吗？

**red flag**：
- 「将来可能要扩展，先抽象好」← 没要求就不抽
- 「加个参数更灵活」← 没用例不加
- 「万一...」← 不在需求里就不处理

### 3. Surgical Changes — 只动该动的

**checklist**：

- [ ] 每一行 diff 都能直接追溯到用户需求吗？
- [ ] 没在「顺手改」相邻代码 / 注释 / 格式
- [ ] 没 refactor 未坏的东西
- [ ] 变更匹配既有风格（哪怕我更喜欢另一种）
- [ ] 我的变更产生的 orphan（未用 import / 变量 / 函数）已清理；**pre-existing 的 dead code 保留，只提醒**

**red flag**：
- 「这个地方顺便 format 一下」← 除非用户要求
- 「这段代码风格不一致，改了吧」← 除非用户要求
- 「这个 import 用不到了，删」← 先判断是你造的 orphan 还是已存在

### 4. Goal-Driven Execution — 先定成功条件，再循环

**checklist**：

- [ ] 把任务转成可验证目标：
  - 「加校验」→「写校验失败的 test，再让它 pass」
  - 「修 bug」→「写复现 bug 的 test，再让它 pass」
  - 「重构 X」→「前后 tests 都 pass」
- [ ] 多步任务写出 plan：每步 → verify: [check]
- [ ] 每步结束执行 verify，再进下一步
- [ ] 弱成功条件（"能跑就行"）必须细化成强条件

**red flag**：
- 「先写完再跑 test」← 不，先 test 后写
- 「看起来差不多」← 成功条件必须可量化
- 「跑一下应该没问题」← 必须真跑

## 优先级与冲突

1. **用户明确指令 > 本 skill**：CLAUDE.md / AGENTS.md / 对话里的直接要求优先
2. **本 skill > 系统默认**：与 default system behavior 冲突时按本 skill
3. **流程型 skill > 本 skill**：`superpowers-brainstorming` / `superpowers-systematic-debugging` / `superpowers-test-driven-development` 若适用，先进它们再回本 skill

## 与其他 skill 的导航

- **开始多步实现任务** → 先 `superpowers-brainstorming`，再本 skill
- **遇到 bug / 意外行为** → 先 `superpowers-systematic-debugging`，再本 skill
- **声称"完成"之前** → `superpowers-verification-before-completion`
- **项目级强制规范** → `autoresearch-house-rules`

## 本 skill 起作用的信号

- diff 更小、更贴需求
- 少出现"顺便改了 X"
- 在 implementation 之前出现 clarifying question（而不是出错后）
- 成功条件在 plan 里被显式写出并被 verify

---
name: selftest-reality-alignment
description: >-
  Ensures automated selftests exercise the same code paths, timing, and
  configuration as interactive runs and reference implementations. Use when
  writing or reviewing selftest.py, debugging "tests pass but real use fails",
  aligning sim/control loops with a baseline (e.g. ASAP), or validating
  physics/RL policies headlessly against ground-truth trajectories.
---

# 自测与真实用例对齐（Selftest–Reality Alignment）

## 何时启用

在以下情况 **必须** 读本 skill 并按清单执行：

- 新增或修改 `scripts/selftest.py`、集成测试、回归用例
- 出现 **自测全过、人工/GUI/实机表现不对**
- 控制系统、仿真步进、多线程/DDS、观测–策略–力矩链路相关开发
- 需要从参考实现（如 ASAP）复现行为并做 A/B

## 核心教训（来自 ASAP Mimic / UHC 对齐实践）

1. **同一路径原则**：自测必须调用与 `run.py` / 生产入口 **相同的** 主循环类（如 `PolicyRunner`），禁止仅用「精简版」直接调 backend + policy 而通过集成却走另一套逻辑。
2. **时序与步进比锁定**：若真实系统为「每控制周期 K 次物理步」或固定控制频率，自测必须 **逐步计数** 驱动，禁止用独立 `time.sleep` 让策略与物理脱耦；否则会出现「飘」「动作发软」等仅在真实节奏下才暴露的问题。
3. **参考时钟**：相位、插值、gap 等应基于 **步数 × control_dt**（或与参考实现一致的时钟），而非 `time.time()`，否则 headless 加速与 GUI 实时会行为不一致。
4. **配置对齐**：与参考实现一致的 **显式配置**（如 `start_upper_dof_pos`、插值后 gap 秒数）必须在自测与交互使用 **同一配置源**；禁止自测硬编码而 profile 另一套。
5. **可观测数值 vs 肉眼**：对动态任务用 **可量化指标**（如骨盆 `z_max`、关节跟踪误差、与参考轨迹的最大偏差）作为 PASS 条件，并尽量与参考 run 的同一指标对比。
6. **并发与数据竞争**：若存在多线程读写仿真状态，自测与真实路径必须使用 **相同的锁/双缓冲策略**；在锁外 `mj_step`、锁内读状态会导致自测与真实都可能「随机」错，但表现不同。
7. **对照脚本**：对关键策略维护 **头less 对照**（同一物理、同一 ONNX、逐步对齐观测/动作/目标关节），用于回归时证明与 baseline 未漂移。

## 自测设计清单（交付前自检）

在合并或交付人工审核前，确认：

- [ ] **入口一致**：自测覆盖的代码路径包含用户实际使用的 `run` 入口与核心编排类。
- [ ] **步进一致**：`steps_per_control`、控制频率、总仿真步数与产品设计一致；无「自测多跑了几倍物理步」。
- [ ] **配置一致**：自测加载的 profile/YAML 与文档中的推荐启动命令一致，或显式说明差异及原因。
- [ ] **场景覆盖**：至少包含「仅 backend」「完整 PolicyRunner」「状态切换（若适用）」；对 mimic 类任务含 **插值 → gap → 策略激活** 全序列。
- [ ] **数值阈值**：阈值有注释来源（参考轨迹、物理合理范围、或历史基线）；关键动态指标有 **与 reference 的对比** 或 recorded baseline。
- [ ] **非交互**：仍保持 headless、无人工输入；键盘/GUI 用注入命令或状态机事件模拟。
- [ ] **失败可诊断**：FAIL 时打印足够上下文（步数、状态、关键标量），便于区分「阈值过严」与「逻辑错误」。

## 反模式（禁止）

- 自测只测「ONNX 能跑通」而不测 **完整控制闭环**。
- 自测用 `time.sleep(0)` 抢跑导致与实时/GUI **不同的策略/物理比**。
- 自测与手动运行使用 **两套** 默认关节目标、插值时长或 gap。
- 以「看起来稳定」为唯一标准，无 **量化** 或与 baseline 的对比。
- 修复 bug 后只跑最小用例，不跑 **全量 selftest** 与关键对照脚本。

## 与项目规范的关系

本 skill 是对仓库级 `DEVELOPMENT_RULES.md` 中「自测先行」的 **细化**：通过 **对齐** 保证自测有效，而非仅「有 selftest 即可」。

## 可选：对照脚本模式

当存在权威参考实现时：

1. 提取与产品相同的观测构造、相位、mask、PD、动作缩放。
2. 在同一 MuJoCo 模型上同步步进，逐帧对比 obs 子集、action、目标关节或骨盆高度曲线。
3. 将最大允许偏差写入 selftest 或独立 `scripts/compare_*` 的退出码。

---

**一句话**：自测的价值在于 **与真实用例同路径、同步调、同配置、可量化对齐**；否则自测通过只说明「某段代码能跑」，不说明产品行为正确。

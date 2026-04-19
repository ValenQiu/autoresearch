# M3.R5 Gate D 差分审查报告（旧=`main` vs 新=`sim2real_debug`）

日期：2026-04-19  
代码仓库：`/home/qiulm/sources/universal_humanoid_controller`  
对比基线：

- old（旧实现）：`main` @ `e1c664a`
- new（新实现）：`sim2real_debug` @ `80c9d46`
- merge-base：`02e7e79`（M3-R 规划指定基线）

---

## 审查结论（先给结论）

- **阻塞级（High）差异：0 项**
- **中风险（Medium）差异：2 项**（见下）
- **低风险（Low）差异：2 项**
- **结论**：新实现分支 `sim2real_debug` 已满足 Gate D 的“技术可审查”前置条件；在补齐中风险项的处置说明后，可作为 M3.R5 的候选闭合版本。

---

## Findings（按严重度）

### Medium-1：模型资产在新分支缺失，影响部分回归可复现性

- 证据：`git diff --name-status main..sim2real_debug` 显示：
  - `D models/beyondmimic/dance2_subject3/2026-04-09_15-20-14_dance2_subject3.onnx`
  - `D models/bfm_zero/reward_inference`
- 影响：不影响 M3 的 Unitree loopback 主链路，但会影响某些跨策略回归场景复现。
- 建议处置：
  - 方案 A：在 `sim2real_debug` 补齐这两项并记录来源；
  - 方案 B：若刻意不跟踪大文件，在文档显式声明“非 Gate D 必需资产”，并提供可下载脚本。

### Medium-2：人工检查脚本在新分支缺失

- 证据：`git diff --name-status main..sim2real_debug` 显示：
  - `D scripts/manual_check_m4_3.sh`
- 影响：对 M3-R loopback 自动化不构成阻塞，但降低人工联调便利性。
- 建议处置：在 M3 口径下可不恢复；若保留 M4 回归路径，建议将该脚本独立迁回或在 runbook 指定替代流程。

### Low-1：配置加载语义发生正向修复（extends deep-merge）

- 证据：`uhc/core/config.py`（`main..sim2real_debug`）
  - 新分支引入 `load_robot_yaml + _deep_merge`，支持 `robot` 的 `extends` 递归合并。
- 影响：修复 `g1_29dof_real.yaml` 基类字段丢失风险，属于**降低风险**改动。

### Low-2：控制链路可观测性与契约语义增强

- 证据：
  - `uhc/backends/unitree_backend.py`：`LowCmd.dq` 有限差分估计、stale 节流日志；
  - `scripts/mock_unitree_mujoco_bridge.py`：时序与 bridge 可观测性增强；
  - `scripts/run.py`：interface/domain 覆盖与 loopback 补丁注入；
  - `uhc/core/policy_runner.py`：`input_source=none/headless` 便于自动化。
- 影响：对 Gate B/C 自动化验收是正向改进。

---

## 差分范围摘要（字段/时序/稳定性/安全）

### 1) 字段语义差异（LowCmd / LowState）

- `LowCmd.dq`：旧实现趋向固定 0；新实现可按 `q_target` 有限差分估计并限幅（更贴近 ASAP 语义）。
- `LowCmd.tau`：新实现仍冻结为 0（与 M3.R1/R2 冻结约束一致）。
- `LowState freshness`：新实现对“对象缺失”和“fresh 时间戳过期”分别处理并告警。

判定：**无高危字段缺失**。

### 2) 时序差异（bridge loop）

- 新实现 bridge 强化了“发布状态/消费命令/步进”的可解释顺序与命令驱动逻辑。
- 未发现不可解释的时序偏移证据。

判定：**可解释、可复现**。

### 3) 稳定性差异（loopback 自测）

- 已验证新分支：
  - `./scripts/selftest_mock_sim2real_chain.sh loopback` PASS
  - `conda run -n robo_deploy python scripts/selftest_loopback_policy_runner_smoke.py --loco` PASS
- 指标上未见回归性失败（`min_z/max_tilt` 在阈值内）。

判定：**无“倒地率上升”证据**。

### 4) 安全差异（timeout/fallback/estop）

- `selftest_real.py` 在新分支 `27/27 PASS`（timeout、冻帧、fallback 覆盖）。
- loopback 状态机路径可稳定到 `E_STOP`。

判定：**无高危安全退化证据**。

---

## 审查命令记录（节选）

```bash
git rev-parse main sim2real_debug && git merge-base main sim2real_debug
git diff --name-status main..sim2real_debug
git range-diff 02e7e79..main 02e7e79..sim2real_debug
./scripts/selftest_mock_sim2real_chain.sh loopback
conda run -n robo_deploy python scripts/selftest_loopback_policy_runner_smoke.py --loco
conda run -n robo_deploy bash scripts/smoke_sim2real.sh preflight
```

---

## Gate D 关闭建议

满足以下两条后，可关闭 Gate D：

1. 对 `models/*` 与 `scripts/manual_check_m4_3.sh` 的缺失给出明确处置（补齐或豁免）；
2. 将本报告路径写入 M3 验收矩阵与任务总表，作为“新旧差分审查”证据链接。

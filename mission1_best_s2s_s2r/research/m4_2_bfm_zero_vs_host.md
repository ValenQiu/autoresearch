# M4.2 通用底座策略选型：BFM-Zero vs HoST

**结论：选择 BFM-Zero**（LeCAR-Lab，ICLR 2026，arXiv:2511.04131）

## 选型理由

1. **29-DOF 完全对齐**：与 UHC `g1_29dof.yaml` 一致，无需额外处理缺失关节（HoST 为 23-DOF，缺 6 个手腕关节）
2. **Promptable**：latent z（256 维）可实现 goal-reaching，为 M4.3 的"全身目标替代上肢插值"提供原生能力
3. **部署栈完整**：deploy 分支提供 ONNX + sim2sim + sim2real 完整流程
4. **能力超集**：BFM-Zero 可通过 goal z 复现 HoST 的 recovery 行为，同时支持 tracking 和 reward 推理
5. **MuJoCo XML 兼容**：与 UHC 现有 `scene_29dof.xml` 质量差仅 0.001kg，ctrlrange 完全一致

## 对比详情

| 维度 | BFM-Zero | HoST |
|------|----------|------|
| 论文 | ICLR 2026，arXiv:2511.04131 | RSS 2025 Best Systems Paper Finalist |
| 机构 | LeCAR-Lab (CMU) | InternRobotics（上海 AI 实验室） |
| DOF | 29（含手腕） | 23（无手腕） |
| 控制方式 | PD，action_rescale=5 | P 控制，action_scale=1 |
| 观测维度 | 465（含 4 帧历史） + 256 z = 721 | 76 x 6 帧 = 456 |
| ONNX 输入 | `[1, 721]` (obs + z) | 需手工导出 |
| ONNX 输出 | `[1, 29]` | 23 |
| 物理 dt | 0.005s | 0.005s |
| Control Hz | 50 | 50 (decimation=4) |
| 可 prompt | z（tracking/goal/reward） | 不可 |
| 质量 | 35.113 kg | N/A（23-DOF URDF） |

## 实现交付物

### UHC 仓库（universal_humanoid_controller）

| 文件 | 说明 |
|------|------|
| `uhc/policies/bfm_zero.py` | `BFMZeroPolicy(BasePolicy)` 子类：ONNX 加载、obs 组装（465 维 + 4 帧历史）、z 管理（goal/tracking/reward） |
| `config/policies/bfm_zero.yaml` | PD gains、action_scale、default_joint_angles、z_sources 配置 |
| `config/profiles/sim2sim_bfm_zero.yaml` | BFM-Zero(base) + BeyondMimic(task) profile |
| `models/bfm_zero/` | ONNX 模型 + 预计算 z 文件（symlinks） |
| `scripts/verify_bfm_zero.py` | 6 项 headless 验证测试 |

### PolicyRunner 改动

| 改动 | 说明 |
|------|------|
| `_create_base_policy()` | 新增方法：根据 `policy_type` 动态加载 base_policy 类，向后兼容 AsapLoco |
| `upper_body_ref` 解耦 | 使用 `get_upper_body_home()` 接口替代直接访问 `upper_body_ref` 属性 |
| `_handle_cmd` 扩展 | 基于 `hasattr` 分发：AsapLoco 保持 wasd 速度控制，BFM-Zero 新增 n/p 切换 goal z |

## 观测组装（关键对齐点）

参照 BFM-Zero deploy 分支 `config/policy/motivo_newG1.yaml` 的观测顺序：

```
dof_pos_minus_default (29)
dof_vel (29)
projected_gravity (3)
base_ang_vel (3, scale=0.25)
prev_actions (29)
--- history (4 frames each) ---
prev_actions_history (4x29=116)
base_ang_vel_history (4x3=12, scale=0.25)
dof_pos_minus_default_history (4x29=116)
dof_vel_history (4x29=116)
projected_gravity_history (4x3=12)
--- latent z ---
z (256)
```

总输入 = 465 + 256 = **721 维**

## 后续（M4.3）

- MuJoCo GUI 端到端 sim2sim 验证（当前为 headless）
- RECOVERING 状态机扩展
- goal z 驱动的全身策略切换过渡
- 跌倒检测 → BFM-Zero goal z 引导站起 → BASE_ACTIVE

## M4.2 集成排障补充（2026-04-16）

在 `sim2sim_bfm_zero_all.yaml` 的 base→task 切换中，出现过两类腰部异常，最终根因与修复如下。

### 现象 A：切换瞬间腰部异常跳变

- 触发条件：进入 task 时插值起点错误地取了历史缓存/零值，而不是当前机器人姿态
- 根因：`PolicyRunner` 的上肢插值起点与真实 `joint_pos` 脱节
- 修复：插值起点统一取切换当帧的实际上肢关节角（`state["joint_pos"][num_lower:]`）

### 现象 B：所有动作在 base→task 都出现腰部前倾

- 触发条件：将插值起点改成 base policy 的最后命令值（`_last_base_q_target`）
- 根因：BFM-Zero 是高方差全身策略，腰部命令值可能与真实姿态偏差很大；从命令值起插值会在 1.5s 内持续命令机器人向该倾斜姿态靠拢，形成可见前倾
- 修复：撤销“命令值起插值”方案，enter/exit 两个方向都改回“实际姿态起插值”

### 插值时长对齐

- BeyondMimic 与 OmniXtreme 的 `loco_to_task_duration_s` 从 `2.5s` 统一到 `1.5s`
- 结果：base↔task 的体感切换时长与 ASAP Mimic 一致

### 可复用排错流程（摘要）

1. 先分离“视觉异常”与“力矩连续性”两个目标，避免单指标优化导致回归
2. 固定 profile + 环境（`robo_deploy`）复现实验，记录腰部三轴 command/actual/gap
3. 对比三种插值起点（zero / command / actual）：
   - zero：位置与力矩都跳变
   - command：力矩连续但会诱导姿态偏转
   - actual：姿态过渡最物理一致，最终选用
4. 修复后做回归：base→task 与 task→base 两个方向都验证

该流程已沉淀为 skill：`uhc-interpolation-debugging`。

# M1.5 验证计划：UHC vs ASAP 一致性对齐

## 结论（2026-04-15）

针对 CR7 等动作的「飘」「腾空感」等问题，已通过 **UHC 实现与 ASAP 对齐** 闭环：同步物理–控制步进比、插值后稳定 gap、`start_upper_dof_pos` 与配置同源、仿真状态读写线程安全、相位/插值基于步数时钟；headless 指标（如骨盆高度极值）与 ASAP 参考一致；**人工确认 ASAP mimic 测试全部通过**。下文 Step 1–5 保留为可选深度验证或后续回归手段；双终端 ASAP 原版并非日常开发必需路径。

## 问题（历史记录）

CR7 mimic 动作在 UHC 中执行时，视觉表现与 ASAP 原版存在差异：
- 跳跃高度可能不符合物理直觉
- 上半身旋转幅度较大
- 需要严格对比确认是实现 bug 还是动作本身特性

## 验证方案

### Step 1: 搭建 ASAP 原版运行环境

在 `robo_deploy` conda 环境中安装 rclpy (robostack):
```bash
conda config --env --add channels conda-forge
conda config --env --add channels robostack-staging
conda install ros-humble-desktop
```

验证 ASAP sim2sim 能正常运行：
```bash
# Terminal 1: MuJoCo sim
cd ~/sources/ASAP/sim2real
python sim_env/base_sim.py --config=config/g1_29dof_hist.yaml

# Terminal 2: Policy
python rl_policy/deepmimic_dec_loco_height.py \
  --config=config/g1_29dof_hist.yaml \
  --loco_model_path=models/dec_loco/.../model_6600.onnx
```

### Step 2: 参考 Unitree 官方仓库确认物理配置

需要交叉对比的参数来源：
1. [unitree_mujoco](https://github.com/unitreerobotics/unitree_mujoco) — MuJoCo MJCF 场景文件、弹性绳实现
2. [unitree_rl_gym](https://github.com/unitreerobotics/unitree_rl_gym) — 训练时的观测/动作空间定义
3. [unitree_rl_lab](https://github.com/unitreerobotics/unitree_rl_lab) — IsaacLab 版训练 + BeyondMimic motion tracking
4. [unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab) — MuJoCo 版训练 + sim2sim/sim2real 部署

需要确认的项目：
- [ ] MJCF 场景文件 (scene_29dof.xml) 与训练环境一致
- [ ] PD gains (kp/kd) 与训练时完全匹配
- [ ] action_scale 与训练时一致
- [ ] default_joint_angles 与训练时一致
- [ ] 观测拼接顺序和 scale 与训练代码完全匹配
- [ ] history handler 初始化和更新逻辑一致
- [ ] DOF mask 逻辑一致 (23 vs 29 DOF)
- [ ] 物理仿真步长 (sim_dt) 和控制频率 (control_hz) 一致

### Step 3: 采集对比数据

在 ASAP 原版和 UHC 中用**完全相同的物理引擎**运行 CR7 动作，记录：
- 每帧的 pelvis xyz + quaternion
- 每帧的 29 关节角度 (q_target vs actual)
- 每帧的观测向量 (obs)
- 每帧的策略输出 (raw action)
- 每帧的 PD 力矩 (tau)

### Step 4: 逐维对比

对比 ASAP 和 UHC 的：
1. obs[0] (第一帧观测) 是否完全一致
2. action[0] (第一帧输出) 是否完全一致
3. 如果 obs/action 一致但物理表现不同 → 物理引擎配置问题
4. 如果 obs 不一致 → 找到第一个 diverge 的维度，定位 bug

### Step 5: 修复并验证

修复发现的差异，直到 UHC 和 ASAP 在 headless 模式下的轨迹完全一致 (pelvis xyz max diff < 1cm)。

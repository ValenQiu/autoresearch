# ASAP sim2real 架构分析报告

**日期**: 2026-04-14  
**目的**: 为 Mission 1 提供技术基础  

## 1. 目录结构

ASAP sim2real 共 20 个文件，结构清晰：

```
sim2real/
├── setup.py
├── state_publisher.py
├── config/g1_29dof_hist.yaml        # 核心配置
├── sim_env/base_sim.py              # MuJoCo sim2sim backend
├── rl_policy/
│   ├── base_policy.py               # 策略基类
│   ├── decoupled_locomotion_stand.py        # Loco 策略（无高度）
│   ├── decoupled_locomotion_stand_height.py # Loco 策略（含高度指令）
│   ├── deepmimic_dec_loco.py                # Loco + Mimic 组合策略
│   ├── deepmimic_dec_loco_height.py         # Loco + Mimic + 高度
│   └── listener_deltaa.py                   # 数据采集
└── utils/
    ├── command_sender.py            # DDS 关节指令发送
    ├── history_handler.py           # 观测历史管理
    ├── key_cmd.py                   # 键盘控制
    ├── recurrent_thread.py          # 周期线程
    ├── robot.py                     # 机器人参数
    ├── ros_cmd.py                   # ROS2 辅助
    ├── state_processor.py           # DDS 状态读取
    ├── test_xbox.py                 # Xbox 测试
    ├── unitree_sdk2py_bridge.py     # SDK 桥接
    └── util.py                      # 工具函数
```

## 2. 继承体系

```
BasePolicy
├── DecoupledLocomotionStandPolicy          # 仅下肢 RL，上肢固定
│   └── DecoupledLocomotionStandHeightPolicy # + 高度指令
└── MotionTrackingDecLocoPolicy             # Loco + 多技能 Mimic 切换
    └── MotionTrackingDecLocoHeightPolicy   # + 高度指令
```

## 3. ONNX 加载方式

```python
# BasePolicy.setup_policy()
session = onnxruntime.InferenceSession(model_path)
input_name = session.get_inputs()[0].name
output_name = session.get_outputs()[0].name
# 推理: session.run([output_name], {input_name: obs})[0]
```

- 不依赖任何 ONNX metadata
- 只用第一个输入和第一个输出
- 所有配置（kp/kd/joint_names/obs_dims）从 YAML 读取

## 4. 两种策略的 I/O

### Locomotion (model_6600.onnx)
- 输入: `actor_obs [1, ~500]` (含 history)
- 输出: `action [1, 12]` (仅 12 个腿关节)
- 动作含义: `q_target = action * 0.25 + default_dof_angles`
- 上肢: 用 `ref_upper_dof_pos` (17 维固定参考) 拼接成 29 维

### Mimic (各技能 ONNX)
- 输入: `actor_obs [1, ~300]` (含 history)
- 输出: `action [1, 23 或 29]` (按 `robot_dofs` mask)
- 动作含义: 同上
- 关节 mask: `g1_29dof_anneal_23dof` 关闭手腕 6 个自由度

## 5. 观测拼接 (Locomotion Height 版)

```python
obs = concat([
    last_action(12),           # 上一帧下肢动作
    base_ang_vel(3) * 0.25,    # 角速度
    ang_vel_command(1),        # 角速度指令
    base_height_command(1)*2,  # 高度指令
    lin_vel_command(2),        # 线速度指令
    stand_command(1),          # 站立/行走标志
    cos_phase(1),              # 步态相位 cos
    dof_pos_err(29),           # 关节偏差
    dof_vel(29) * 0.05,        # 关节速度
    history(...),              # 历史观测展平
    projected_gravity(3),      # 投影重力
    ref_upper_dof_pos(17),     # 上肢参考
    sin_phase(1)               # 步态相位 sin
])
```

## 6. 状态切换机制

### Loco → Mimic
1. 按 `[` (或手柄 select) 翻转 `policy_locomotion_mimic_flag`
2. 上肢从当前 `ref_upper_dof_pos` 插值到 `start_upper_body_dof_pos[skill]` (~1.5s)
3. 插值完成后切换 `self.policy = policies_mimic[idx]`
4. 重置 `history_handler`

### Mimic → Loco
1. 动作完成 (`phase >= 1.0`) 自动切回
2. 或按 `[` 紧急切回
3. 上肢从当前位置插值回 `loco_upper_body_dof_pos`

### 急停
1. 按 `o`: `use_policy_action = False`
2. `q_target = 当前关节位置` (零速度 PD hold)
3. 不发送额外力矩

## 7. PD Gains (ASAP G1 29DoF)

```yaml
# 腿部 (12 关节): 适中刚度，保证动态平衡
MOTOR_KP: [100, 100, 100, 200, 20, 20, 100, 100, 100, 200, 20, 20]
MOTOR_KD: [2.5, 2.5, 2.5, 5, 0.2, 0.1, 2.5, 2.5, 2.5, 5, 0.2, 0.1]

# 腰部 (3 关节): 高刚度
MOTOR_KP: [400, 400, 400]
MOTOR_KD: [5.0, 5.0, 5.0]

# 手臂 (14 关节): 低刚度
MOTOR_KP: [90, 60, 20, 60, 4, 4, 0, 90, 60, 20, 60, 4, 4, 4]
MOTOR_KD: [2.0, 1.0, 0.4, 1.0, 0.2, 0.2, 0.2, 2.0, 1.0, 0.4, 1.0, 0.2, 0.2, 0.2]
```

对比 standby_controller (motion_tracking_controller):
- 腿部 kp=350 (vs ASAP 100-200): 过高，纯 PD 会产生过大纠正力矩
- ASAP 的 kp 较低是因为 RL 策略本身提供了动态平衡能力

## 8. 关节顺序 (ASAP 29DoF)

```
0:  left_hip_pitch_joint     12: waist_yaw_joint
1:  left_hip_roll_joint      13: waist_roll_joint
2:  left_hip_yaw_joint       14: waist_pitch_joint
3:  left_knee_joint          15: left_shoulder_pitch_joint
4:  left_ankle_pitch_joint   16: left_shoulder_roll_joint
5:  left_ankle_roll_joint    17: left_shoulder_yaw_joint
6:  right_hip_pitch_joint    18: left_elbow_joint
7:  right_hip_roll_joint     19: left_wrist_roll_joint
8:  right_hip_yaw_joint      20: left_wrist_pitch_joint
9:  right_knee_joint         21: left_wrist_yaw_joint
10: right_ankle_pitch_joint  22: right_shoulder_pitch_joint
11: right_ankle_roll_joint   23-28: right arm (同 left)
```

注意: 此顺序与 BeyondMimic ONNX metadata 中的 `joint_names` 可能不同，切换时需要做映射。

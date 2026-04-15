# M1.5 执行计划：ASAP Mimic 切换 + 操作流程打磨

**Milestone**: M1.5  
**范围**: sim2sim, ASAP loco ↔ ASAP mimic  
**前置**: M1 完成  
**预估工作量**: 1-2 天  

## 为什么先做 M1.5

ASAP mimic 与 ASAP loco 共享：
- 相同 PD gains（kp/kd 来自同一 YAML）
- 相同关节顺序（canonical order，无需 JointMapper）
- 相同 action_scale (0.25)
- 相同 default_joint_angles

这意味着 loco↔mimic 切换**不涉及 kp/kd 插值、关节重排、action_scale 切换**。
可以专注于打磨：
- 上肢插值流程（进入/退出 task 时）
- phase-driven 自动切回
- 多技能选择（`;` / `'` 切换）
- 整体操作体验

M2 (BeyondMimic) 在此基础上只需额外处理参数差异。

## 验收标准

- [ ] AsapMimicPolicy 加载技能 ONNX 并执行动作
- [ ] 按 `]` 从 loco 进入 mimic：上肢在 loco 控制下平滑插值 → 策略切换
- [ ] 按 `[` 从 mimic 切回 loco：腿部即时由 loco 接管 → 上肢插值回 ref
- [ ] phase >= 1.0 时自动切回 loco
- [ ] 按 `;` / `'` 在 loco 模式下切换不同 mimic 技能
- [ ] 切换 10 次不摔倒
- [ ] selftest 全部 PASS

## 需要实现的模块

### 1. AsapMimicPolicy (~150 行)
- 加载单个 mimic ONNX
- DOF mask 从输出维度自动推断
- phase = elapsed / motion_length → 0~1
- phase >= 1.0 自动通知切回
- 观测拼接（mimic 模式）：last_action_masked + ang_vel + dof_pos_masked + dof_vel_masked + gravity + phase

### 2. PolicyRunner 切换逻辑扩展 (~100 行)
- 进入 task 前：上肢在 loco 上插值到 task 首帧目标 (1.5s)
- 退出 task 后：上肢在 loco 上插值回 upper_body_reference (1.5s)
- 多 task policy 注册 + `;`/`'` 切换

### 3. 自测扩展 (~80 行)
- Test 7: ASAP mimic 策略加载 + 推理
- Test 8: loco→mimic→loco 切换稳定性 (500 steps per phase)
- Test 9: 多次切换不摔倒

## 需要的模型文件

从 ASAP 复制一个 mimic 技能 ONNX 用于测试：
```
models/mimic/kick_level1/model_168000.onnx
```

## 操作流程（完整版，M1.5 交付后）

```
启动 → 弹性绳吊着 (PASSIVE)
  按 i → 插值到 default pose (BASE_ACTIVE, hold 模式)
  按 ] → 启动 loco 策略 (BASE_ACTIVE, policy 模式)
  按 9 → 松弹性绳 → 机器人站稳
  按 = → 切换站立/行走
  按 w/s/a/d → 速度控制
  
  按 ] → 上肢插值 → 切入 mimic (TASK_ACTIVE)
  动作执行中... phase 进度条显示
  phase=1.0 → 自动切回 loco (BASE_ACTIVE)
  上肢插值回 ref → 回到稳定站姿
  
  按 ; → 切换到下一个技能
  按 ] → 再次执行新技能
  
  按 o → 急停 (E_STOP)
  按 i → 重置 (PASSIVE → BASE_ACTIVE)
```

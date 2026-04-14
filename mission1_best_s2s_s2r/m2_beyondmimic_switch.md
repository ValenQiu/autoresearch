# M2 执行计划：BeyondMimic 适配 + 策略切换

**Milestone**: M2  
**范围**: sim2sim 多策略  
**前置**: M1 完成  
**预估工作量**: 2-3 天  

## 验收标准

- [ ] BeyondMimic 策略独立运行舞蹈动作
- [ ] 按 `]` 从 BASE→TASK 平滑切换（含上肢插值）
- [ ] 按 `[` 从 TASK→BASE 切换后 pelvis_z > 0.35m 持续 3s
- [ ] 反复切换 10 次不摔倒
- [ ] SafetyGuard 在 pelvis_z < 0.3m 时自动 E_STOP
- [ ] 自动化测试覆盖以上场景

## 需要实现的模块

### 1. BeyondMimicPolicy (~200 行)
- 双输入 ONNX：`obs [1, 160]` + `time_step [1, 1]`
- 从 ONNX metadata 读取 `joint_stiffness`, `joint_damping`, `action_scale`
- 观测拼接参考 C++ MotionOnnxPolicy
- 关节顺序映射（ASAP 顺序 ↔ BeyondMimic 顺序）

### 2. PolicyManager 策略切换 (~100 行)
- BASE→TASK: 上肢从 loco ref 插值到 BeyondMimic init pose (~1.5s)
- TASK→BASE: 直接切换 active_policy，ASAP loco 即时接管
- PD gains 同步切换（ASAP kp/kd ↔ BeyondMimic joint_stiffness）

### 3. SafetyGuard (~60 行)
- pelvis 高度监控
- 关节位置/速度限位
- 触发自动 E_STOP

### 4. 自动化测试 (~80 行)
- 脚本化事件序列：BASE(3s) → TASK(10s) → BASE(3s) × 5
- 每次切换后检查 pelvis_z 稳定性
- 输出 PASS/FAIL

## 关键风险

| 风险 | 缓解 |
|------|------|
| BeyondMimic 观测拼接顺序错误 | 从 C++ 代码逐维对齐 |
| ASAP/BeyondMimic 关节顺序不同 | 用 joint_names 做映射 |
| PD gains 切换冲击 | 10 cycle 线性插值过渡 |

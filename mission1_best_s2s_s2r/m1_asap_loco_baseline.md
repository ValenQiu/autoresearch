# M1 执行计划：核心框架 + ASAP Locomotion 基线

**Milestone**: M1  
**范围**: sim2sim (MuJoCo)  
**前置**: M0 完成  
**预估工作量**: 2-3 天  

## 验收标准

- [ ] `python scripts/run.py --profile sim2sim_loco.yaml` 单终端启动 MuJoCo + 策略
- [ ] ASAP locomotion (model_6600.onnx) 控制机器人站立
- [ ] 按 `i` 初始化 → 按 `]` 启动策略 → 机器人行走
- [ ] 按 `o` 急停 → 机器人静止 hold
- [ ] 支持 `--model_path` 本地路径和 `--wandb_path` WandB 拉取
- [ ] 自动化测试：站立 5 秒 pelvis_z > 0.35m

## 需要实现的模块

### 1. MujocoBackend (~150 行)
- 参考 ASAP `base_sim.py`
- 单进程或子线程运行 MuJoCo viewer
- 接口：`read_state()` → (q, dq, quat, ang_vel)，`write_action(q_target, kp, kd)`

### 2. AsapLocoPolicy (~200 行)
- 参考 ASAP `decoupled_locomotion_stand_height.py`
- `prepare_obs()`: 按 ASAP 训练代码拼接观测
- `get_action()`: ONNX 推理 → action * scale + default_pos → 拼接上肢 ref
- HistoryHandler 管理观测历史

### 3. StateMachine (~80 行)
- PASSIVE / BASE_ACTIVE / E_STOP (TASK_ACTIVE 在 M2)
- 状态转移 + guard 条件

### 4. PolicyRunner 主循环 (~100 行)
- 50Hz 循环：read_state → policy.step → write_action
- 管理 backend、policy、state_machine、input

### 5. InputHandler (~60 行)
- 键盘监听 (sshkeyboard)
- 事件映射到状态机指令

### 6. ModelLoader (~40 行)
- 本地路径：直接返回
- WandB path：`wandb.Api().run(path).file("model.onnx").download()`

# M1 执行计划：核心框架 + ASAP Locomotion 基线

**Milestone**: M1  
**范围**: sim2sim (MuJoCo)  
**状态**: ✅ **完成** (2026-04-14)  

## 验收结果

- [x] `python scripts/run.py --profile sim2sim_loco.yaml` 单终端启动 MuJoCo + 策略
- [x] ASAP locomotion (model_6600.onnx) 控制机器人站立
- [x] 按 `i` 初始化 → 按 `]` 启动策略 → 按 `9` 松弹性绳 → 机器人站稳
- [x] 按 `o` 急停 → 机器人静止 hold
- [x] 速度控制键 w/s/a/d/q/e/z/= 正常工作
- [x] 模型加载支持本地路径和 WandB
- [x] 自动化测试 39/39 PASS

## 交付物

### 核心模块
| 文件 | 功能 | 行数 |
|------|------|------|
| `uhc/backends/mujoco_backend.py` | 单进程 MuJoCo + 弹性绳 + PD 控制 | ~190 |
| `uhc/policies/asap_loco.py` | ASAP locomotion 策略 (ONNX + 观测拼接 + history) | ~180 |
| `uhc/core/policy_runner.py` | 主循环 (ASAP 三阶段: hold→init→policy) | ~170 |
| `uhc/input/keyboard.py` | 键盘输入 (SM 事件 + 速度命令) | ~55 |
| `uhc/core/config.py` | 分层配置加载 | ~60 |
| `uhc/core/state_machine.py` | PASSIVE/BASE_ACTIVE/TASK_ACTIVE/E_STOP | ~60 |
| `uhc/core/model_loader.py` | 本地 + WandB 模型加载 | ~50 |
| `uhc/core/safety_guard.py` | 高度/关节限位检查 | ~35 |

### 自测
| 指标 | 结果 |
|------|------|
| 总测试数 | 39 |
| 通过 | 39 |
| 关键指标: pelvis_z final | 0.739m |
| 关键指标: pelvis_z min | 0.725m |
| 关键指标: 弹性绳释放后稳定 | ✅ (min_z_stable=0.729m > 0.25m) |

### 修复的 Bug
1. PD gains kp YAML 解析错误 (29 个值被截断为 16 个)
2. sim loop 死锁 (_lock 重入)
3. 弹性绳释放后 xfrc_applied 残留
4. ASAP 三阶段控制流缺失 (hold/init/policy 模式)

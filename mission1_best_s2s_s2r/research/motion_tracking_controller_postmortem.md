# motion_tracking_controller 复盘报告

**日期**: 2026-04-14  
**目的**: 记录 dummy_task 的技术债和教训，避免在 Mission 1 中重蹈覆辙  

## 1. 核心问题

### 问题 1: 模型加载是假的

`models/base/model_6600.onnx` (ASAP locomotion, 1.7MB) 存在于仓库中，但：

- Python `OnnxPolicyAdapter` 加载它时 `use_python_onnx_runtime=false`（默认值），**连 onnxruntime session 都没创建**
- 即使创建了 session，`step()` 用全零 dummy 输入推理，**输出直接丢弃**
- C++ 端没有任何代码加载这个文件
- 这个文件在系统中完全是摆设

### 问题 2: 模型格式不兼容

| | model_6600.onnx (ASAP) | MotionTrackingController 要求 |
|---|---|---|
| 输入 | `actor_obs [1, 500]` | `obs [1, 160]` + `time_step [1, 1]` |
| 输出 | `action [1, 12]` | `actions [1, 29]` + 5 个额外输出 |
| metadata | 空 | 必须有 joint_names, joint_stiffness 等 |

即使尝试加载，也会立即 crash。

### 问题 3: TASK→BASE 切换必摔

根因：切回 BASE 后控制机器人的是 `StandbyController`——纯 PD 控制器（kp=350 腿）驱动到固定 `default_position`。

纯 PD 控制器：
- 没有动态平衡能力（不调整质心、不调整脚步）
- 从静止启动可以站住（初始姿态接近目标）
- 从动态舞蹈姿态切回必摔（高 kp 突然纠正 → 巨大力矩 → 失稳）

前 agent 的修复尝试：
1. 全身线性插值 blend → 失败（walking_controller kp≈100 太弱，hold 不住中间姿态）
2. ASAP-style 即时切换 → 失败（standby_controller 是纯 PD，不是 ASAP RL）
3. 降低 selftest 的 fall 阈值到 z < 0 → 自欺欺人

### 问题 4: 控制器切换有延迟

`ros2 control switch_controllers` 是 subprocess 调用，两步切换（先 deactivate 再 activate）之间有 1+ 秒的控制真空。后来改为原子切换解决了这个问题，但根本问题（PD 无法恢复）仍在。

### 问题 5: C++ 过度设计

| 功能 | C++ 实现 | Python 等价 |
|------|---------|------------|
| 控制器切换 | subprocess("ros2 control switch_controllers") 270 行 + 6 层 fallback | 赋值 `active_policy = new_policy` |
| 观测拼接 | C++ ObservationTerm 插件体系 | `np.concatenate([...])` |
| ONNX 推理 | C++ onnxruntime + 自定义张量管理 | `session.run(output, {input: obs})[0]` |
| 状态机 | Python runtime_m1.py 2358 行 | ASAP base_policy.py 中 ~50 行 |

## 2. 时间线

1. dummy_task 初始设计：C++ ros2_control + Python 状态机编排
2. M1 开发：反复修复 TASK→BASE 切换摔倒
3. 发现 model_6600.onnx 从未被加载
4. 发现 StandbyController 是纯 PD
5. 发现两者格式完全不兼容
6. 决策：放弃 C++ ros2_control 路线，基于 ASAP 重构

## 3. 教训

1. **验证端到端数据流**：在写状态机之前，先确认模型能被正确加载、推理结果能到达关节
2. **不要用 stub 占位关键功能**：`OnnxPolicyAdapter.step()` 是一个无害但无用的 stub，掩盖了模型未接入的事实
3. **RL 部署不需要 ros2_control**：50Hz 的 RL 策略推理用 Python + onnxruntime 足够，C++ 控制器框架是负担不是助力
4. **训练代码和部署代码的语言一致性很重要**：用 C++ 重写 Python 训练代码的观测拼接逻辑极易出错，且难以验证

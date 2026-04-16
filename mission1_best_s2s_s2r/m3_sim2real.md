# M3 执行计划：Sim2Real 真机部署

**Milestone**: M3  
**范围**: G1 真机 + 安全体系 + 多输入  
**前置**: M2 完成（BeyondMimic sim2sim 已验收）  
**预估工作量**: 3-5 天  
**状态**: 待开始

---

## 目标

将 sim2sim 跑通的全套流程（loco + BeyondMimic + 策略切换）**原封不动地搬到 G1 真机**。PolicyRunner、所有 Policy 类、SafetyGuard 均不修改，只替换底层 Backend。

```
[ M2 完成的部分，不动 ]             [ M3 新增/修改 ]
PolicyRunner                      UnitreeBackend (新增)
  AsapLocoPolicy         ──►      ├── Unitree SDK2 DDS 通信
  BeyondMimicPolicy               ├── 心跳监控 + 通信超时保护
  AsapMimicPolicy                 ├── 力矩限幅（真机更保守）
  SafetyGuard            ──►      └── 关节速度限幅
                                  
                                  XboxHandler (新增)
                                  
                                  sim2real_g1.yaml (新增)
                                  
                                  selftest_real.py (新增，部分 headless)
```

---

## 验收标准

**headless 可验证**（提交前必须 PASS）：
- [ ] UnitreeBackend 接口与 MujocoBackend 完全兼容（相同 `read_state` / `write_action` 签名）
- [ ] DDS 初始化/断连/重连逻辑通过单元测试（mock DDS）
- [ ] 安全保护：心跳超时 → E_STOP，关节限幅有效，力矩钳位有效
- [ ] Xbox 手柄 key 映射与键盘键位一一对应
- [ ] selftest_real.py mock 模式全部 PASS

**人工验收**（真机操作，按顺序执行）：
- [ ] 真机 `PASSIVE → BASE_ACTIVE`：机器人站起，稳定站立 ≥ 5s
- [ ] `BASE_ACTIVE → loco 行走`：速度命令有响应，无明显摇晃
- [ ] `BASE_ACTIVE → TASK_ACTIVE`（BeyondMimic 舞蹈）：切换平滑，不跌倒
- [ ] `TASK_ACTIVE → BASE_ACTIVE`：切回后恢复稳定站立
- [ ] 反复切换 5 次不摔倒
- [ ] 通信断开（拔网线）→ 自动 E_STOP 并打印日志
- [ ] 按 `o` 急停 → 机器人原地停稳

---

## M3.0：环境与依赖准备

### 目标
确保 unitree_sdk2py 在 `robo_deploy` 环境中可用，G1 网络连通。

### 任务
1. 检查 `unitree_sdk2py` 是否已安装（`robo_deploy` 环境）
2. 若未安装：`pip install unitree_sdk2py` 或按官方文档从源码安装
3. 确认 G1 的 `DOMAIN_ID` 和网络接口（通常是 `eth0` 或 `enp*`），写入 `g1_29dof.yaml`
4. 新增 `config/robots/g1_29dof_real.yaml`（继承 sim 版，覆盖通信参数和安全阈值）

```yaml
# config/robots/g1_29dof_real.yaml（真机覆盖参数）
_base: g1_29dof.yaml    # 继承 sim 版全部参数

communication:
  domain_id: 0
  interface: "enp2s0"   # 实际网卡名，需现场确认

safety:
  pelvis_z_min: 0.25          # sim: 0.3，真机稍宽松（防止误触发）
  joint_vel_limit: 15.0       # rad/s，真机关节速度上限
  effort_scale: 0.8           # 力矩安全系数，乘以 ONNX 输出

sim:
  enable_elastic_band: false  # 真机不需要弹性带
```

### 交付物
- `config/robots/g1_29dof_real.yaml`
- 环境验证脚本：`scripts/check_real_env.py`（检查 SDK 版本、网络、DDS）

---

## M3.1：UnitreeBackend 实现

### 目标
实现与 MujocoBackend 完全兼容的 `UnitreeBackend`，通过 Unitree SDK2 DDS 读写 G1 状态。

### 接口对齐（必须与 MujocoBackend 一致）

```python
class UnitreeBackend(HardwareBackend):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
    def read_state(self) -> dict[str, np.ndarray] | None: ...
    def write_action(self, q_target, kp, kd) -> None: ...
    def get_body_id(self, name: str) -> int: ...  # BeyondMimic 需要
```

### 状态读取映射

| UHC `read_state()` key | Unitree SDK2 来源 | 备注 |
|------------------------|-----------------|------|
| `joint_pos[29]` | `LowState.motor_state[i].q` | 按 `motor_mapping` 重排 |
| `joint_vel[29]` | `LowState.motor_state[i].dq` | 同上 |
| `quat[4]` | `LowState.imu_state.quaternion` | SDK 顺序 `(w,x,y,z)` 需确认 |
| `ang_vel[3]` | `LowState.imu_state.gyroscope` | 机体系，直接用 |
| `base_lin_vel[3]` | `LowState.imu_state.accelerometer` 积分 或 状态估计 | ⚠️ 见下方说明 |
| `base_pos[3]` | 无直接来源（真机无绝对位置） | 用 (0,0,z_est) 近似，z 由 pelvis 高度估计 |
| `pelvis_z` | 通过关节正运动学估算，或 IMU 积分 | 安全监控用 |
| `body_xpos/xquat/xmat` | 通过 Pinocchio/简化 FK 计算 | BeyondMimic anchor obs 需要 |

> **`base_lin_vel` 真机方案**：G1 SDK 不直接提供世界系线速度。两种选择：
> 1. **IMU 加速度积分**（简单，有漂移）：`v += (acc_world - g) * dt`
> 2. **状态估计器**（推荐）：参考 ASAP `StateEstimator` 或 STIP 实现
>
> M3 优先用方案 1，验证通过后再升级方案 2。

### 指令发送

```python
def write_action(self, q_target, kp, kd):
    # G1 SDK LowCmd: 每个电机设置 mode=1(Servo), q, dq=0, kp, kd, tau=0
    for i in range(self.num_joints):
        motor_idx = self.motor_mapping[i]
        cmd.motor_cmd[motor_idx].mode = 1
        cmd.motor_cmd[motor_idx].q   = float(q_target[i])
        cmd.motor_cmd[motor_idx].dq  = 0.0
        cmd.motor_cmd[motor_idx].kp  = float(kp[i])
        cmd.motor_cmd[motor_idx].kd  = float(kd[i])
        cmd.motor_cmd[motor_idx].tau = 0.0
    self._publisher.Write(cmd)
```

### 通信安全
- **心跳超时**：`read_state()` 连续 N 帧（默认 5 帧 = 100ms）未收到新数据 → 返回 `None` → PolicyRunner 进入 E_STOP
- **DDS 重连**：连接中断后自动尝试重连（最多 3 次），超过则 E_STOP
- **CRC 校验**：SDK 内置，不需额外处理

### BeyondMimic anchor obs 的真机 FK

BeyondMimic 需要 `body_xpos`, `body_xquat`, `body_xmat`（各 body 的世界系位姿）。真机 SDK 不提供这些，需要正运动学：

```
方案 A（简化）：只计算 anchor body（torso_link）的位姿
  torso_pos ≈ base_pos + R_base @ offset_torso
  torso_R   = R_base @ R_joints_up_to_torso

方案 B（完整）：加载 URDF，用 Pinocchio 计算全身 FK
  import pinocchio as pin
  pin_model = pin.buildModelFromUrdf("g1.urdf")
  pin.forwardKinematics(pin_model, pin_data, q)
```

M3 先用方案 A，后续升级。

### 交付物
- `uhc/backends/unitree_backend.py`
- `uhc/utils/state_estimator.py`（线速度估计）
- `uhc/utils/simple_fk.py`（简化正运动学，用于 anchor obs）

---

## M3.2：安全体系增强

### 目标
真机安全比仿真严格 10 倍，任何异常必须立即 E_STOP。

### 新增安全检查

| 检查项 | 阈值（可配置） | 触发动作 |
|--------|--------------|---------|
| 通信心跳超时 | 100ms 无数据 | 立即 E_STOP + 打印 |
| pelvis_z 过低 | < 0.25m（真机） | E_STOP |
| 关节速度过大 | > 15 rad/s（任意关节） | E_STOP |
| 力矩超限 | > `effort_limit * safety_scale` | 钳位（不急停，但记录） |
| IMU 姿态异常 | roll/pitch > 45° | E_STOP |
| 控制频率跌落 | 实际 Hz < 40Hz（目标 50Hz） | 警告 + 降级 |
| 关节位置超限 | 超出 URDF joint limit | 钳位 + 警告 |

### PolicyRunner 安全扩展

```python
# 真机模式追加的安全检查（在 _step() 末尾）
if backend_type == "unitree":
    if state.get("imu_roll_pitch_max", 0) > 0.785:  # 45°
        self._handle_event(Event.E_STOP)
    if state.get("max_joint_vel", 0) > joint_vel_limit:
        self._handle_event(Event.E_STOP)
```

### E_STOP 行为（真机版）

真机 E_STOP 不能只停策略，需主动让关节阻尼制动：

```python
# E_STOP 状态：kp=0，kd=适中，q_target=当前位置（阻尼停止）
elif self.sm.state == State.E_STOP:
    q_target = state["joint_pos"].copy()
    kp = np.zeros(self.num_joints)
    kd = np.full(self.num_joints, 2.0)  # 纯阻尼，真机安全
```

---

## M3.3：Xbox 手柄支持

### 目标
用 Xbox 手柄替代键盘作为真机主输入，保持与键盘相同的语义。

### 按键映射

| Xbox 按键 | 功能 | 键盘等效 |
|-----------|------|---------|
| `START` | init（站起） | `i` |
| `B` | 激活 loco | `]` |
| `X` | 切换 loco ↔ task | `[` |
| `BACK` | E_STOP | `o` |
| `LB/RB` | 切换 task 策略 | `;` / `'` |
| 左摇杆 XY | 线速度命令 | `wasd` |
| 右摇杆 X | 转向命令 | `qe` |
| 左摇杆按下 | 速度清零 | `z` |
| `Y` | 步态切换（站立/行走） | `=` |

### 实现依赖
- `pygame`（已在 ASAP 环境中安装）
- `uhc/input/xbox.py`：继承 `BaseInputHandler`，实现相同的 `_handle_event` / `_handle_cmd` 回调接口

---

## M3.4：Sim2Real Profile + 启动脚本

### 新增配置

```yaml
# config/profiles/sim2real_g1_loco.yaml
robot: config/robots/g1_29dof_real.yaml

backend:
  type: unitree
  domain_id: 0
  interface: "enp2s0"
  state_timeout_ms: 100

base_policy:
  config: config/policies/asap_loco.yaml
  model_path: models/base/model_6600.onnx

input_source: xbox    # 真机用手柄
```

```yaml
# config/profiles/sim2real_g1_bm.yaml
robot: config/robots/g1_29dof_real.yaml

backend:
  type: unitree
  domain_id: 0
  interface: "enp2s0"
  state_timeout_ms: 100

base_policy:
  config: config/policies/asap_loco.yaml
  model_path: models/base/model_6600.onnx

task_policies:
  - name: beyondmimic_dance
    config: config/policies/beyondmimic.yaml
    wandb_path: liuming-valen-qiu-the-hong-kong-polytechnic-university/g1_lafan1_motion_tracking/8ma9qhx9

input_source: xbox
```

### PolicyRunner 中的 backend 分发

```python
# policy_runner.py setup()
if backend_type == "mujoco":
    from uhc.backends.mujoco_backend import MujocoBackend
    self.backend = MujocoBackend(robot_cfg, backend_cfg)
elif backend_type == "unitree":
    from uhc.backends.unitree_backend import UnitreeBackend
    self.backend = UnitreeBackend(robot_cfg, backend_cfg)
```

### 启动命令

```bash
# sim2sim（开发调试用）
python scripts/run.py --profile config/profiles/sim2sim_loco_beyondmimic.yaml

# sim2real（真机用）
python scripts/run.py --profile config/profiles/sim2real_g1_bm.yaml
```

---

## M3.5：Selftest 与验收

### headless 可测部分（`scripts/selftest_real.py`）

```
Test 1: UnitreeBackend 接口兼容性
  - 用 MockUnitreeSDK 替换真实 DDS
  - 验证 read_state() 返回正确 key/shape
  - 验证 write_action() 调用 motor_cmd 正确

Test 2: 安全保护触发
  - mock 高度 < 0.25m → 验证触发 E_STOP
  - mock 关节速度 > 15 rad/s → 验证触发 E_STOP
  - mock 心跳超时 → 验证触发 E_STOP
  - mock IMU 翻滚 > 45° → 验证触发 E_STOP

Test 3: Xbox 手柄映射
  - 模拟 START 按下 → 验证 Event.INIT 触发
  - 模拟摇杆输入 → 验证速度命令更新

Test 4: Sim2Real Profile 加载
  - 加载 sim2real_g1_loco.yaml
  - 验证 backend_type == "unitree"
  - 验证 input_source == "xbox"
  - 验证安全阈值比 sim 更保守
```

### 真机人工验收（操作手册）

**准备**：
1. G1 上电，确认机器人处于悬空或支架保护状态
2. 运行 `python scripts/check_real_env.py` 确认网络/DDS/SDK 连通
3. 运行 `python scripts/run.py --profile config/profiles/sim2real_g1_loco.yaml`

**验收序列**：

```
Step 1  机器人悬空 → 按 START（init）→ 关节插值到默认姿态
        ✓ 无异常运动，关节平滑到位

Step 2  放下机器人（或移走支架）→ 按 B（激活 loco）
        ✓ 机器人站立稳定 ≥ 5s，pelvis_z > 0.55m

Step 3  左摇杆前推 → 行走
        ✓ 有行走响应，无明显摇晃

Step 4  按 X → 切换到 BeyondMimic
        ✓ 切换平滑，机器人开始舞蹈动作

Step 5  按 X → 切回 loco
        ✓ 恢复站立，pelvis_z > 0.35m

Step 6  重复 Step 4-5 共 5 次
        ✓ 全部不摔倒

Step 7  强制断开网络 → 等待 100ms
        ✓ 自动 E_STOP，控制台打印超时日志

Step 8  按 BACK 急停
        ✓ 机器人阻尼停止，关节不飞车
```

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| `base_lin_vel` 真机估计不准 | 高 | 中（策略退化但不摔） | M3 先跑 loco（不需线速度）；BeyondMimic 后续再调优 |
| Pinocchio FK 接入复杂 | 中 | 中（anchor obs 不准） | 先用简化 FK（仅 torso），后续升级 |
| 真机 PD gains 需调参 | 高 | 高（不稳定或跌倒） | 保守开始：kp×0.7，逐步增加；悬空测试后再落地 |
| Xbox 库在机器人端不可用 | 低 | 低（退回键盘） | 检测到无手柄时自动降级到键盘 |
| G1 SDK 版本不兼容 | 低 | 高（无法通信） | M3.0 环境检查时验证；备选用 unitree_legged_sdk |

---

## 开发顺序

```
M3.0  环境检查（1h）
  └─► M3.1  UnitreeBackend（1-2天）
        ├─► M3.2  安全增强（半天）
        ├─► M3.3  Xbox 手柄（半天）
        └─► M3.4  Profile + 启动脚本（1-2h）
              └─► M3.5  selftest + 人工验收（1天）
```

---

## 关键文件清单

| 新增/修改 | 说明 |
|-----------|------|
| `uhc/backends/unitree_backend.py` | 新增：UnitreeBackend 主体 |
| `uhc/utils/state_estimator.py` | 新增：线速度积分估计 |
| `uhc/utils/simple_fk.py` | 新增：简化正运动学（torso anchor） |
| `uhc/input/xbox.py` | 新增：Xbox 手柄处理 |
| `config/robots/g1_29dof_real.yaml` | 新增：真机参数覆盖 |
| `config/profiles/sim2real_g1_loco.yaml` | 新增：loco 真机 profile |
| `config/profiles/sim2real_g1_bm.yaml` | 新增：loco+BM 真机 profile |
| `scripts/check_real_env.py` | 新增：真机环境检查 |
| `scripts/selftest_real.py` | 新增：真机相关 headless 测试 |
| `uhc/core/policy_runner.py` | 修改：添加 unitree backend 分发 + 真机安全检查 |
| `uhc/core/safety_guard.py` | 修改：扩展真机安全阈值（速度/姿态/心跳） |

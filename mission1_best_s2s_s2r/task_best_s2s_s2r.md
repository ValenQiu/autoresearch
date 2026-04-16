# Mission 1: Best Sim2Sim & Sim2Real Controller

**版本**: v2.0  
**创建日期**: 2026-04-14  
**状态**: Active  

## 1. 目标

构建一个 **SOTA 级别的通用 sim2sim & sim2real 人形机器人运控部署工具**。

核心要求：
- 支持任意 RL 策略 ONNX 模型的即插即用部署（ASAP / BeyondMimic / HoST / 自定义）
- sim2sim 和 sim2real 共享同一套策略编排代码，仅 backend I/O 不同
- 开发迭代零编译：新增模型类型只需 Python 代码 + YAML 配置
- 从训练代码到部署代码的 gap 最小化
- 模型来源支持本地路径和 WandB 拉取

## 2. 技术路线

### 2.1 架构决策

- **独立新项目**，不直接修改 ASAP 或 motion_tracking_controller
- **Python + onnxruntime + DDS** 架构（参考 ASAP sim2real，但解耦）
- **ROS2 仅用于可选工具层**（可视化/录包），不参与控制回路
- **环境**：conda 环境 + Docker 容器双轨支持

### 2.2 代码来源

从 ASAP 和 motion_tracking_controller 中按需复制、重构：
- ASAP `base_policy.py` / `utils/` / `base_sim.py` → 核心控制循环和 I/O
- ASAP `config/g1_29dof_hist.yaml` → 拆分为 robot 配置 + 策略配置
- motion_tracking_controller `MotionOnnxPolicy.cpp` → BeyondMimic 观测拼接参考
- `model_6600.onnx` → ASAP locomotion 模型

### 2.3 与 dummy_task 的关系

dummy_task 已废弃。复盘见 `research/motion_tracking_controller_postmortem.md`。

## 3. 需求清单

### R0. 项目基建
- 独立项目，不与 ASAP/BeyondMimic 仓库耦合
- conda 环境 + Docker 容器双轨
- 一键安装/启动脚本
- agent/skill/workflow 工具确保跨机器、跨人协作

### R1. 简化配置结构
- ASAP 的单一巨型 YAML 拆分为：
  - **robot 配置**：关节名、限位、默认姿态、PD gains（按机器人型号）
  - **策略配置**：观测拼接顺序、action scale、history 设置（按策略类型）
  - **profile 配置**：运行时参数（选哪个 robot、哪个 base/task 策略、backend 选择）
- 移除 ASAP 中大量的 per-skill 配置（start_upper_body_dof_pos、mimic_models 等），这些属于具体策略，不属于框架

### R2. 代码结构优雅简明
- 参考 ASAP 但不照搬，优化代码组织
- 模块化：策略注册、观测拼接、硬件后端、状态机均为独立模块
- 接口精简：每个模块暴露最少的公共 API

### R3. 交互体验
- 单终端启动（不再手动开两个终端）
- sim 进程由框架自动管理
- 保留键盘/手柄交互方式（沿用 ASAP 键位）

### R4. 模块化与可扩展
- PolicyRegistry：注册/发现策略类型
- ObservationBuilder：配置驱动的观测拼接
- HardwareBackend：抽象 sim/real 接口
- ActionMapper：action → joint target 映射
- 新增策略类型 = 新建 Policy 子类 + YAML 配置，不改框架

### R5. 模型来源
- 本地 ONNX 文件路径
- WandB run path 自动下载
- 统一的模型加载接口

## 4. 系统架构

```
┌─────────────────────────────────────────────────────┐
│  PolicyRunner (单进程，50Hz 主循环)                    │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ StateMachine │  │ InputHandler │  │ SafetyGuard  │  │
│  │ PASSIVE      │  │ keyboard     │  │ height check │  │
│  │ BASE_ACTIVE  │  │ xbox         │  │ joint limits* │  │
│  │ TASK_ACTIVE  │  │ unitree_rc   │  │ auto e-stop  │  │
│  │ E_STOP       │  │              │  │              │  │
│  └──────┬───────┘  └──────────────┘  └─────────────┘  │
│         │                                              │
│  ┌──────▼────────────────────────────────────────┐    │
│  │ PolicyManager                                   │    │
│  │  ┌─────────────────────────────────────────┐   │    │
│  │  │ PolicyRegistry                           │   │    │
│  │  │  "asap_loco"  → AsapLocoPolicy           │   │    │
│  │  │  "beyondmimic"→ BeyondMimicPolicy        │   │    │
│  │  │  "host"       → HostPolicy (future)      │   │    │
│  │  └─────────────────────────────────────────┘   │    │
│  │  base_policy: registry["asap_loco"](cfg)       │    │
│  │  task_policy: registry["beyondmimic"](cfg)      │    │
│  └──────┬────────────────────────────────────────┘    │
│         │                                              │
│  ┌──────▼──────────────┐  ┌────────────────────────┐  │
│  │ ObservationBuilder  │  │ ModelLoader             │  │
│  │ (配置驱动拼接)       │  │ local path / WandB     │  │
│  └─────────────────────┘  └────────────────────────┘  │
│         │                                              │
│  ┌──────▼────────────────────────────────────────┐    │
│  │ HardwareBackend                                │    │
│  │  MujocoBackend (sim2sim, 内嵌 subprocess)      │    │
│  │  UnitreeBackend (sim2real, DDS 直连)            │    │
│  └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

\* **joint limits**：默认对目标关节角做 URDF 裁剪；高动态 task 策略可设 `skip_position_clip`，与参考 deploy（仅力矩/包络限幅）一致。

## 5. 项目目录结构

```
universal_humanoid_controller/          ← 新独立项目
├── README.md
├── setup.py / pyproject.toml
├── environment.yml                     ← conda 环境定义
├── Dockerfile                          ← Docker 构建
├── docker_run.sh                       ← Docker 一键启动
├── install.sh                          ← conda 一键安装
│
├── config/
│   ├── robots/
│   │   └── g1_29dof.yaml              ← 机器人定义（关节名/限位/默认姿态/PD gains）
│   ├── policies/
│   │   ├── asap_loco.yaml             ← ASAP locomotion 观测/动作配置
│   │   ├── asap_mimic.yaml            ← ASAP mimic 配置
│   │   └── beyondmimic.yaml           ← BeyondMimic 配置
│   └── profiles/
│       ├── sim2sim_loco_bm.yaml       ← 运行 profile：MuJoCo + ASAP loco + BeyondMimic
│       └── sim2real_g1.yaml           ← 运行 profile：G1 真机
│
├── uhc/                                ← 核心包 (universal_humanoid_controller)
│   ├── __init__.py
│   ├── core/
│   │   ├── state_machine.py
│   │   ├── policy_runner.py            ← 主循环
│   │   ├── policy_registry.py          ← 策略注册/发现
│   │   ├── safety_guard.py
│   │   └── model_loader.py             ← 本地 + WandB 模型加载
│   ├── policies/
│   │   ├── base_policy.py              ← 策略基类
│   │   ├── asap_loco.py                ← ASAP locomotion
│   │   ├── asap_mimic.py               ← ASAP mimic
│   │   └── beyondmimic.py              ← BeyondMimic
│   ├── observation/
│   │   ├── builder.py                  ← 配置驱动观测拼接
│   │   └── transforms.py              ← quat_rotate_inverse 等
│   ├── backends/
│   │   ├── base_backend.py             ← 抽象接口
│   │   ├── mujoco_backend.py           ← sim2sim
│   │   └── unitree_backend.py          ← sim2real
│   ├── input/
│   │   ├── keyboard.py
│   │   ├── xbox.py
│   │   └── unitree_remote.py
│   └── utils/
│       ├── history.py                  ← 观测历史管理
│       └── math.py
│
├── models/                             ← 本地模型存放
│   └── base/
│       └── model_6600.onnx
│
├── scripts/
│   ├── run.py                          ← 统一入口
│   └── test_suite.py                   ← 自动化测试
│
└── tests/
    └── test_state_machine.py
```

## 6. 状态机

```
        ┌──────────┐
   ┌────┤ PASSIVE  │◄──────────────────────┐
   │    └────┬─────┘                       │
   │  [i]    │ init interpolation          │ [i] reset
   │         ▼                              │
   │    ┌──────────┐                       │
   │    │BASE_ACTIVE│◄──────────┐          │
   │    └────┬─────┘           │          │
   │  []]    │ activate task   │ [[] back  │
   │         ▼                 │          │
   │    ┌──────────┐           │          │
   │    │TASK_ACTIVE├──────────┘          │
   │    └────┬─────┘                      │
   │         │                             │
   │    [o] e-stop (任意状态)               │
   │         ▼                             │
   │    ┌──────────┐                      │
   └────┤ E_STOP   ├─────────────────────┘
        └──────────┘
```

## 7. Milestones

### M0: 项目基建与环境配置
**目标**：项目骨架、开发环境、CI 基础设施就绪。任何人在任何机器上能一键搭建环境。

**交付物**：
- [ ] 独立项目仓库 + 目录结构
- [ ] `environment.yml` + `install.sh`（conda 一键安装）
- [ ] `Dockerfile` + `docker_run.sh`（Docker 一键启动）
- [ ] 基础 Python 包结构（`uhc/`）可 import
- [ ] 配置加载框架（robot / policy / profile YAML）
- [ ] agent skill / workflow 文档

### M1: 核心框架 + ASAP Locomotion 基线
**目标**：在 sim2sim (MuJoCo) 中用 ASAP locomotion 策略控制机器人站立/行走。

**交付物**：
- [ ] MujocoBackend：单终端启动，sim 进程自动管理
- [ ] AsapLocoPolicy：加载 `model_6600.onnx`，观测拼接，推理，关节控制
- [ ] StateMachine：PASSIVE → BASE_ACTIVE → E_STOP 全流程
- [ ] InputHandler：键盘控制（`i` 初始化 / `]` 启动 / `o` 急停）
- [ ] 模型加载支持本地路径和 WandB
- [ ] 自动化测试：站立稳定性 + 行走稳定性

### M1.5: ASAP Mimic 切换 + 操作流程打磨 ✅（已完成 2026-04-15）

**目标**：在 M1 基础上接入 ASAP Mimic，完成 loco↔mimic 切换与多技能选择，行为与 ASAP 参考对齐。

**交付物**：
- [x] AsapMimicPolicy：ONNX、DOF mask、phase、观测与 history
- [x] PolicyRunner：上肢插值、与 ASAP 一致的 gap 与 `start_upper_dof_pos`、同步物理步进
- [x] 多 mimic 技能 profile（如全技能列表）与键位（`]` / `[` / `;` / `'`）
- [x] headless 自测 + 与 ASAP 对照脚本/指标（对齐动态表现）
- [x] 人工验收：mimic 表现与验收标准一致

**说明**：实现与验收在独立仓库 `universal_humanoid_controller` 完成；详见 `m1_5_asap_mimic_switch.md`。

### M2: BeyondMimic 适配 + 策略切换 ✅（已完成 2026-04-15）

**目标**：BeyondMimic 作为 task 策略加入，实现 loco↔task 稳定切换。

**交付物**：
- [x] BeyondMimicPolicy：加载 BeyondMimic ONNX，双输入推理（obs + time_step）
- [x] metadata 自描述：joint_names/kp/kd/action_scale/default_pos/anchor_body 全部从 ONNX 读取
- [x] JointMapper：处理 BeyondMimic L-R 交替序 vs 机器人标准序的映射
- [x] 上肢插值：正确坐标系转换（两端 remap 到机器人序后相减）
- [x] 锚点观测：worldToInit 变换 + 6D 旋转表示（行主序对齐 C++ 参考）
- [x] base_lin_vel 机体系转换：quat_rotate_inverse 与 IsaacLab 训练对齐
- [x] motion_length_s 自动解析：WandB motion artifact (.npz) → 225.68s
- [x] phase 计算与 phase_complete 自动返回
- [x] PD gains 插值（loco kp/kd → BeyondMimic kp/kd 线性过渡）
- [x] SafetyGuard：高度监控 + 自动 E_STOP
- [x] selftest 76/76 PASS（含插值阶段 + 30% 片段 + Phase 完整运行）

**说明**：详见 `m2_beyondmimic_switch.md`。

---

#### M2 调试经验教训

**1. 关节顺序是新网络适配的第一优先级**

BeyondMimic 使用 L-R 交替排列（`left_hip_pitch, right_hip_pitch, waist_yaw, left_hip_roll, ...`），ankles 混在 shoulders 之间，与 ASAP 的机器人标准序完全不同。若忽略这一点：
- 错误 1：`get_upper_body_target()` 中只对 `_ref_joint_pos` 做 remap，但对 `default_angles` 直接 slice，导致两者在不同序下相减，产生 ±2 rad 虚假偏移，机器人插值时摔倒
- 教训：凡涉及 policy 序 → robot 序转换，`default_angles`、`_ref_joint_pos`、`kp/kd` **全部**都要走 `JointMapper`，不能只转换其中一个

**2. 观测帧（world vs body）要对齐训练环境**

MuJoCo `qvel[0:3]` 是**世界系**线速度，而 IsaacLab 的 `base_lin_vel` obs 是**机体系**（经过 `quat_rotate_inverse` 转换）。C++ 中间层通常已做这个转换，仅凭"C++ 直接用 `v_[0:3]`"就认为不需要转换是错误结论。规则：凡观测名称含 `_b`（body frame），必须检查是否需要旋转。

**3. phase / motion_length_s 的来源必须是真实时长**

WandB run summary 的 `Train/mean_episode_length` 是训练 episode 超时长（约 10s），不是动作片段的真实时长（225.68s）。必须从 **WandB motion artifact (.npz)** 中读取 `joint_pos.shape[0] / fps` 才是正确值，否则 phase 会在 10s 时就虚假完成，触发错误自动返回。

**4. 分段测试策略**

- 插值效果验证：只需跑插值时长（如 2.5s）+ 稳定 gap（1s），无需全量，节省大量时间
- 稳定性验证：运行 30% 时长（约 67s）即可检验切换稳定性和短时 drift
- phase/终止条件验证：必须跑 100%（11284 steps for dance2_subject3）
- selftest 各阶段步数应从 policy config 读取，不得硬编码

### M3: Sim2Real + 安全体系 + 多输入
**目标**：在 G1 真机上跑通全流程。PolicyRunner 和所有 Policy 类不改动，只替换底层 Backend。

**子阶段**：

- **M3.0 环境准备**：`unitree_sdk2py` 安装验证；`g1_29dof_real.yaml`（通信/安全阈值覆盖）；`check_real_env.py` 连通性检查
- **M3.1 UnitreeBackend**：与 MujocoBackend 完全兼容接口；`read_state()` 映射 SDK LowState；`write_action()` 输出 LowCmd；心跳超时检测；`base_lin_vel` IMU 积分估计；简化 FK 计算 anchor body obs
- **M3.2 安全体系增强**：增加关节速度限幅、IMU 姿态异常检测（roll/pitch > 45°）、控制频率监控；E_STOP 真机阻尼制动模式（kp=0, kd=适中）
- **M3.3 Xbox 手柄支持**：`uhc/input/xbox.py`；与键盘完全相同的语义映射；无手柄时自动降级键盘
- **M3.4 Profile 与启动**：`sim2real_g1_loco.yaml`、`sim2real_g1_bm.yaml`；PolicyRunner backend 分发逻辑
- **M3.5 测试与验收**：`selftest_real.py`（mock DDS 全覆盖）；真机人工验收操作手册

**交付物**：
- [ ] `uhc/backends/unitree_backend.py`
- [ ] `uhc/utils/state_estimator.py`（线速度积分）
- [ ] `uhc/utils/simple_fk.py`（anchor body 简化 FK）
- [ ] `uhc/input/xbox.py`
- [ ] `config/robots/g1_29dof_real.yaml`
- [ ] `config/profiles/sim2real_g1_loco.yaml` / `sim2real_g1_bm.yaml`
- [ ] `scripts/check_real_env.py`
- [ ] `scripts/selftest_real.py`（mock 模式全 PASS）
- [ ] 真机人工验收：5 次 loco↔BeyondMimic 切换不摔倒

**详见**：`m3_sim2real.md`

### M4: 多策略在线切换 + 通用底座

**目标**：将 UHC 从"单次切换"升级为"多策略在线切换"，并引入通用底座替代固定站立姿态，实现任意姿态自主恢复与全身目标插值。

**M4 总进度（2026-04）**：

| 子阶段 | 状态 | 说明 |
|--------|------|------|
| **M4.1** 多策略透明中转 | ✅ **已完成** | `PolicyRunner`：`;`/`'` + `_pending_task_switch_idx`，详见 `m4_multi_policy_switch.md` |
| **M4.2** 通用底座选型 | ✅ **已完成** | BFM-Zero 选定 + `BFMZeroPolicy` 实现 + headless 验证通过，详见 `research/m4_2_bfm_zero_vs_host.md` |
| **M4.3** 通用底座集成 | 🚧 待开始 | `RECOVERING`、`universal_base.py` |
| **M4.4** OmniXtreme | ✅ **已完成** | sim2sim 验收、`skip_position_clip`、复盘与 skill |

**M4.2 集成进展更新（2026-04-16）**：
- [x] 修复 base↔task 上肢插值起点错误导致的腰部异常跳变（起点改为切换当帧实际关节角）
- [x] 修复“命令值起插值”引入的全动作腰部前倾回归（enter/exit 均改为实际姿态起插值）
- [x] 对齐切换时长：BeyondMimic / OmniXtreme 的 `loco_to_task_duration_s` 统一到 `1.5s`
- [x] 排错流程沉淀：新增 skill `uhc-interpolation-debugging`

**子阶段**：

**M4.1：多策略在线切换（Plan A 透明中转）** ✅ **已完成（代码）**

- `; / '` 在 TASK_ACTIVE 状态下触发 TASK→loco(加速)→TASK' 的透明中转
- PolicyRunner：`_pending_task_switch_idx` 排队机制（与 loco 退出插值衔接）
- 验收（产品级）：sim2sim 中 BeyondMimic→CR7→BeyondMimic 连续切换 5 次不摔倒 — **建议用多 task profile 做一次专项回归**；机制已在 `PolicyRunner` 中实现
- 详见：`m4_multi_policy_switch.md`

**M4.2：通用底座策略调研与选型（HoST vs BFM-Zero）** ✅ **已完成（2026-04-16）**

> **选型结论：BFM-Zero**（LeCAR-Lab，ICLR 2026）

| 维度 | **HoST** | **BFM-Zero** ✅ |
|------|----------|-------------|
| 类型 | 单一 recovery 策略 | 可 prompt 行为基础模型 |
| DOF | 23-DOF（缺手腕） | **29-DOF（与 UHC 完全一致）** |
| 能力 | 跌倒→站立（fixed behavior） | goal-reaching / tracking / reward，latent z prompt |
| 开源状态 | 有论文，权重依托于具体实现 | ✅ checkpoint + ONNX + sim2sim + sim2real 均已开源 |
| ONNX 导出 | 需手工适配 | ✅ 原生支持（opset 13，输入 721 维） |
| Promptable | ❌ | ✅ latent z（256 维）驱动行为 |
| MuJoCo XML 兼容 | 需要适配 | ✅ 与 UHC `scene_29dof.xml` 质量/ctrlrange 一致（Δ0.001kg） |

交付物：
- `uhc/policies/bfm_zero.py`：`BFMZeroPolicy(BasePolicy)` 子类，完整 obs 组装 + 4 帧历史 + z 管理
- `config/policies/bfm_zero.yaml`：PD gains / action_scale / z_sources 全部逐字复制自 deploy 参考
- `config/profiles/sim2sim_bfm_zero.yaml`：BFM-Zero(base) + BeyondMimic(task) profile
- `PolicyRunner._create_base_policy()`：动态 base_policy 加载，向后兼容 AsapLoco
- `scripts/verify_bfm_zero.py`：6 项 headless 验证（obs 维度、目标 z、tracking z、动态加载）
- 详见 `research/m4_2_bfm_zero_vs_host.md`

**M4.3：通用底座集成**
- 将 BFM-Zero 正式接入 UHC 作为 `base_policy`（M4.2 已实现基础 `BFMZeroPolicy` 类）
- 状态机新增 `RECOVERING` 状态：跌倒检测 → RECOVERING(BFM-Zero goal z 引导站起) → BASE_ACTIVE
- 策略切换时：目标策略的 `get_full_body_target()` → BFM-Zero 接受 goal z → 自主全身过渡（替代手工上肢插值）
- MuJoCo GUI 端到端验收（M4.2 仅完成 headless 验证）
- 验收：机器人从躺倒 → BFM-Zero 自主站起 → 进入 BeyondMimic → 结束后返回站立

**M4.4：OmniXtreme / 高动态策略接入** ✅ sim2sim 已验收（2026-04-16）

- 将 [OmniXtreme](https://github.com/Perkins729/OmniXtreme) 等高动态策略作为新 task_policy 接入
- 与 BeyondMimic 相同的封闭式 ONNX 接口（state → action）
- 需对齐 OmniXtreme 的 obs 结构（flow-matching base policy + residual）
- 验收：OmniXtreme 高动态动作在 sim2sim 中稳定执行（含与 PolicyRunner 同路径的 `skip_position_clip` 修复）

**进展摘要**：

已完成：
- [x] `OmniXtremePolicy` 实现（双策略 Base FM + Residual，3 个 ONNX 模型）
- [x] `MotionReferenceSource`：.npz 参考动作加载，FK ONNX anchor body 计算
- [x] `JointMapper`：BeyondMimic motionlib 序 ↔ URDF 标准序转换
- [x] 观测管线对齐参考 `deploy_mujoco.py`（real_obs, command_obs, residual_obs, history buffer）
- [x] `initial_noise` 修复（FM 策略的去噪起点，从 zeros 改为 `np.random.randn()`）
- [x] Actuator envelope clipping（torque-speed 包络限位，X1/X2/Y1/Y2 参数直接逐字复制自参考）
- [x] Per-substep friction model（`MujocoBackend.set_friction()`，不再用 position 近似）
- [x] MuJoCo XML 对齐（使用参考 `no_hand.xml`，正确的质量 33.3kg + ctrlrange 139Nm hip）
- [x] `simulate_dt` 配置化（0.004，5 substeps，匹配参考的 decimation=5）
- [x] `SafetyGuard` 高度阈值策略级覆盖（OmniXtreme 地面动作需 `safety_min_height: 0.0`）
- [x] Friction 生命周期管理（TASK_ACTIVE 激活，EXIT 清除）
- [x] Headless 长程稳定测试通过
- [x] **根因修复**：`SafetyGuard.clip_action()` 与 URDF 位置限位对高动态策略过严 → `skip_position_clip` + `PolicyRunner` 条件跳过（详见 `research/omnixrtreme_uhc_adaptation.md`）
- [x] 复盘文档与 Cursor skill：**`research/omnixrtreme_uhc_adaptation.md`**、**`.cursor/skills/uhc-policy-adaptation/SKILL.md`**（后续新增模型适配默认遵循）

**调试经验教训**：
1. **参考代码的"bug"也是训练数据**：X1_list 的 formatting 差异虽然在物理上"不正确"，但策略就是用这些值训练的，"修正"反而引入不匹配
2. **Position-based friction 补偿不等价于 per-substep friction**：前者用初始 dq 估算一次，后者每个 substep 用实时 dq 更新，高动态场景差异显著
3. **MuJoCo XML 不同 = 完全不同的物理世界**：质量差 1.77kg、hip 力矩限差 60%，直接导致无法复现参考行为
4. **FM 策略的 `initial_noise` 是必需的**：不是可选的探索噪声，而是 flow matching 去噪链的输入起点
5. **框架默认 `clip_action` 可能破坏策略**：参考 `deploy_mujoco.py` 不对关节目标做 URDF 位置裁剪；UHC 若裁剪，高动态段会在数百步内失稳。策略若已有包络/力矩路径，应 `skip_position_clip: true`。

**交付物（M4 汇总）**：
- [x] **M4.1** PolicyRunner 多策略在线切换（`_pending_task_switch_idx` + `;`/`'`，见 `m4_multi_policy_switch.md`）
- [ ] **M4.2** 选型报告（调研文档：HoST vs BFM-Zero）
- [ ] **M4.3** `uhc/policies/universal_base.py`（HoST 或 BFM-Zero 适配）
- [ ] **M4.3** `uhc/core/state_machine.py`：新增 RECOVERING 状态
- [x] **M4.4** `uhc/policies/omnixrtreme.py` 及 `config/policies/omnixrtreme.yaml`
- [x] **M4.4** `scripts/debug_omnixrtreme_audit.py`（数值对比 / 回归辅助）
- [ ] 自动化测试更新（多策略切换专项 + M4.3 recovery 流程）

---

### M5: 通用追踪器 + 参考动作流式输入

**目标**：UHC 从"策略 = 单一 ONNX + 固定动作"升级为"通用追踪器 + 实时参考动作流"。一个 ONNX 追踪无限种动作，参考动作来源可以是文件、手柄、遥操设备。

**架构变化**：
```
现有（封闭式）：  Policy.get_action(state) → q_target
升级后（开放式）：TrackerPolicy.get_action(state, motion_ref) → q_target
                 motion_ref 由 MotionProvider 每 tick 提供
```

**子阶段**：

**M5.1：MotionProvider 抽象层**
- `uhc/motion/provider.py` → `MotionProvider` 基类
- `FileMotionProvider`：从 `.npz`/`.pkl` 读取离线动作序列（BFM-Zero 格式 / LAFAN1）
- `StreamMotionProvider`：从 ZMQ 接收实时帧
- 数据格式：`{joint_pos, joint_vel, body_pos, body_quat, phase}`

**M5.2：OpenTrack 适配** ← 优先
- 官方 ONNX 导出路径清晰（`brax2onnx_tracking` → `mj_onnx_video` 已验证）
- LAFAN1 generalist v1 权重**直接可用**，零训练成本
- DAgger 路径与本机现有 16 个 ASAP 专家策略天然衔接：专家 rollout → DAgger 蒸馏 → 通用 ONNX
- 参考：[GalaxyGeneralRobotics/OpenTrack](https://github.com/GalaxyGeneralRobotics/OpenTrack)

**M5.3：BFM-Zero Tracker 模式**
- BFM-Zero 支持 tracking_inference：给定参考动作 → 提取 latent z → 追踪执行
- 接入 UHC 的 TrackerPolicy 接口（也可兼用 M4 中的底座角色）
- 参考：[LeCAR-Lab/BFM-Zero](https://github.com/LeCAR-Lab/BFM-Zero) deploy branch

**M5.4：SONIC / GR00T-WBC 适配**
- SONIC 是通用追踪器：`obs = [state_obs, reference_motion_command]`
- 主要增量为 Kinematic Planner + VR 遥操栈，直接对接 M6
- 本机已有 `mj_retargeting/pico_protoc/tracking.proto`（Pico 协议基础已就绪），与 SONIC ZMQ 栈天然对接
- 参考：[NVlabs/GR00T-WholeBodyControl](https://github.com/NVlabs/GR00T-WholeBodyControl)

**M5.5：Kinematic Planner（SONIC）**
- SONIC 附带的运动风格 planner：选风格 + 速度/高度 → 实时生成参考动作 → 追踪器跟踪
- 新增 `uhc/motion/kinematic_planner.py`（实现 MotionProvider 接口）

**M5 选型依据**：
> OpenTrack 先于 SONIC 的原因：① ONNX 导出路径更成熟 ② generalist 权重直接可用 ③ DAgger 范式可复用本机 16 个 ASAP 专家策略（天然 teacher） ④ 与 BeyondMimic 同属 LAFAN1 体系。SONIC 的主要增量（Planner + VR）在 M6 遥操阶段更能发挥价值，且本机 Pico 协议已就绪。

**交付物**：
- [ ] `uhc/motion/provider.py`（MotionProvider 抽象）
- [ ] `uhc/motion/file_provider.py`（.npz/.pkl 离线读取）
- [ ] `uhc/motion/stream_provider.py`（ZMQ 实时接收）
- [ ] `uhc/policies/opentrack.py`
- [ ] `uhc/policies/sonic_tracker.py`
- [ ] `uhc/motion/kinematic_planner.py`
- [ ] OpenTrack sim2sim LAFAN1 generalist 跟踪验收
- [ ] SONIC sim2sim LAFAN1 跟踪验收

---

### M6: 遥操作（Teleoperation）

**目标**：参考动作来源从文件变为实时人类输入设备，实现真人→机器人的实时动作迁移。

**子阶段**：

**M6.1：Pico VR 接入**
- `uhc/motion/pico_vr_provider.py`：通过 ZMQ 接收 Pico VR 6DoF 头部 + 双手数据
- 协议参考 SONIC 的 ZMQ Manager / PICO VR 文档（v4 header 1280 bytes）
- 本机已有 Pico 协议基础：`/home/qiulm/sources/mj_retargeting/pico_protoc/tracking.proto`

**M6.2：Retarget Pipeline**
- `uhc/motion/retarget.py`：人体骨架 → G1 关节角实时映射
- 本机已有完整 pipeline：`/home/qiulm/sources/mj_retargeting/`（离线+实时 retarget，GUI，MuJoCo）
- 可复用 SONIC 的 retarget，或基于 BFM-Zero 的 SMPL retarget

**M6.3：MoCap 接入**
- `uhc/motion/mocap_provider.py`：从光学/惯性 MoCap 系统接收全身轨迹
- 延迟优化目标：VR < 50ms，MoCap < 20ms

**验收**：戴上 Pico → 手臂移动 → 机器人实时跟随（sim2sim 先验证）

---

### M7: 高层自主性（Planner / VLM / VLA）

**目标**：参考动作来源从人类变为 AI，接入规划器和大模型实现语言/视觉驱动的机器人行为。

**子阶段**：

**M7.1：Text-to-Motion**
- 接入 Kimodo 等 text-to-motion 模型（SONIC 网页 demo 已集成）
- `uhc/motion/text_to_motion_provider.py`：自然语言 → 参考动作序列 → 追踪器执行

**M7.2：VLM / VLA 行为规划**
- `uhc/planning/vla_planner.py`：视觉 + 语言指令 → 行为序列 → 运动子目标 → 追踪器执行

**M7.3：感知-规划-控制闭环**
- 摄像头/LiDAR → 感知 → VLA 规划 → MotionProvider → 追踪器 → 执行 → 反馈

## 8. ASAP 配置精简分析

ASAP `g1_29dof_hist.yaml` 有 571 行。按用途分类：

| 内容 | 行数 | 保留策略 |
|------|------|---------|
| 机器人基础定义（joint names, limits, default pos, PD gains, motor mapping） | ~120 行 | → `config/robots/g1_29dof.yaml` |
| 观测维度定义（obs_dims, obs_loco_dims, obs_mimic_dims, obs_scales） | ~50 行 | → `config/policies/asap_loco.yaml` 等 |
| History 配置（history_config, history_loco_config, etc.） | ~50 行 | → 对应 policy 配置 |
| 步态参数（GAIT_PERIOD, phase 相关） | ~5 行 | → policy 配置 |
| Per-skill 初始上肢姿态（start_upper_body_dof_pos：12 个技能） | ~120 行 | **移除**：属于具体 mimic 技能，不属于框架 |
| Per-skill 模型映射（mimic_models, mimic_robot_types, motion_length_s） | ~80 行 | **移除**：由技能 YAML 自描述 |
| robot_dofs mask | ~10 行 | → mimic policy 配置（如需） |
| Sim 参数（SIMULATE_DT, VIEWER_DT, scenes） | ~20 行 | → backend 配置 |
| 通信参数（DOMAIN_ID, INTERFACE） | ~5 行 | → profile 配置 |
| 手柄配置（USE_JOYSTICK, JOYSTICK_TYPE） | ~5 行 | → profile 配置 |
| 杂项（flags, constants） | ~30 行 | 按需保留 |

**精简后**：框架核心配置 ~250 行（robot + policy + profile），比原来 571 行减少 56%。Per-skill 配置独立为每个技能的小 YAML 文件。

## 附录 A: dummy_task 复盘

见 `research/motion_tracking_controller_postmortem.md`。

## 附录 B: ASAP 架构分析

见 `research/asap_sim2real_analysis.md`。

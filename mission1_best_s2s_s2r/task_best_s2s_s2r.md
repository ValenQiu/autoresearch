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
│  │ BASE_ACTIVE  │  │ xbox         │  │ joint limits │  │
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

### M2: BeyondMimic 适配 + 策略切换
**目标**：BeyondMimic 作为 task 策略加入，实现 loco↔task 稳定切换。

**交付物**：
- [ ] BeyondMimicPolicy：加载 BeyondMimic ONNX，双输入推理
- [ ] PolicyManager：base/task 策略切换（PD gains 同步切换）
- [ ] BASE→TASK 切换（含上肢插值过渡）
- [ ] TASK→BASE 切换（ASAP loco 即时接管，保持平衡）
- [ ] SafetyGuard：高度监控、关节限位、自动 E_STOP
- [ ] 自动化测试：切换 10 次不摔倒

### M3: Sim2Real + 安全体系 + 多输入
**目标**：在 G1 真机上跑通全流程。

**交付物**：
- [ ] UnitreeBackend：DDS 通信接入 G1
- [ ] 真机安全保护：通信中断自动 E_STOP、力矩限幅
- [ ] Xbox 手柄支持
- [ ] 真机 smoke test（PASSIVE → BASE → TASK → BASE → E_STOP）

### M4: 多策略扩展 + HoST + 生产化
**目标**：支持多策略在线切换，集成 HoST，工具级打磨。

**交付物**：
- [ ] 运行时多 task 策略切换（ASAP mimic 技能库）
- [ ] HoST recovery 策略集成
- [ ] 一键启动脚本 + 配置模板 + 文档
- [ ] 自动化回归测试套件
- [ ] 性能 profiling

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

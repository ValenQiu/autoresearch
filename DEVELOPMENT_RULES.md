# Autoresearch 开发规范

所有在 autoresearch 项目体系下的自动化开发项目 **必须** 遵循以下规范。

## 1. 自测先行（Selftest-First Development）

### 核心原则

**Agent 交付给人工审核的每一个功能，必须先通过自动化自测。**

人工审核者扮演的是产品经理角色——只给功能性反馈，不做 debugger。Agent 必须自行验证所有技术细节。

### 自测要求

1. **每个项目必须有 `scripts/selftest.py`**（或等价的自测入口）
2. **selftest 必须 headless**：不依赖 GUI、不依赖人工键盘输入、不依赖真实硬件
3. **selftest 必须涵盖完整链路**：
   - 配置加载 → 模块初始化 → 核心功能 → 输出验证
4. **selftest 必须有明确的 PASS/FAIL 判定**：
   - 每个检查点有数值化的通过标准（如 `pelvis_z > 0.3m`）
   - 最终输出 `N/M passed, K failed`
5. **每次代码修改后必须跑 selftest**：
   - 新功能：先写 selftest case，再实现功能
   - Bug 修复：先复现 failure case，修复后确认 PASS
   - 提交前：全量 selftest PASS

### selftest 模板

```python
#!/usr/bin/env python3
"""项目自测脚本 — 自动化验证所有功能。"""

class SelfTestResult:
    def __init__(self):
        self.tests = []

    def check(self, name: str, passed: bool, detail: str = ""):
        self.tests.append((name, passed, detail))
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

    def summary(self) -> int:
        passed = sum(1 for _, p, _ in self.tests if p)
        total = len(self.tests)
        print(f"\nSELFTEST: {passed}/{total} passed, {total - passed} failed")
        return 0 if passed == total else 1

def main():
    r = SelfTestResult()
    # ... 各模块测试 ...
    return r.summary()

if __name__ == "__main__":
    raise SystemExit(main())
```

### 自测设计原则

- **模拟外部依赖**：如需仿真物理引擎，用 headless 步进代替 GUI viewer
- **数值化验证**：用具体阈值（如高度、关节误差）而非视觉判断
- **分层测试**：先测基础模块，再测集成链路
- **快速反馈**：单次 selftest 应在 30 秒内完成

### 自测与真实用例对齐（强制）

**仅有 selftest PASS 不够**：自测必须通过 **与真实使用方式对齐** 的设计，才能拦截「测试全过、人工一跑就错」类问题。

1. **代码路径对齐**
   - 集成类自测必须走与 `run.py`（或统一入口）**相同的主循环与编排**（例如同一 `PolicyRunner` / 状态机），禁止长期依赖仅调用底层模块的「捷径用例」作为唯一回归依据。
   - 若存在捷径用例，须在注释或文档中说明其与主路径的差异及风险。

2. **时序与步进对齐**
   - 控制周期、每周期物理子步数（如 `steps_per_control`）、总步数须与产品设计一致；**禁止**用与主循环无关的 `time.sleep` 或不同步频让策略与仿真脱耦。
   - 时间相关逻辑（相位、插值、延时、gap）优先使用 **步数 × dt** 或与参考实现一致的时钟，避免 headless 加速与 GUI/实机实时行为不一致。

3. **配置与数据对齐**
   - 自测加载的 profile/默认值须与推荐给用户的启动方式 **一致**，或显式覆盖并在测试中说明；禁止自测写死一组关节目标而交互界面使用另一套配置。

4. **可量化与可选 baseline**
   - 对动态、接触、腾空等难凭肉眼判定的行为，必须定义 **数值指标**（如质心/骨盆高度极值、关节跟踪误差、与参考轨迹的最大偏差）。
   - 若存在权威参考（如上游 ASAP），应维护 headless **对照脚本**或录制的参考指标，重大改动时对比未漂移。

5. **并发与状态一致性**
   - 若仿真或硬件接口有多线程，自测路径须与生产路径使用 **相同** 的同步策略（锁、双缓冲等）；禁止「单线程自测过、多线程实跑炸」。

6. **覆盖切换与全序列**
   - 凡产品支持模式切换、插值、延时激活的，自测须包含 **完整序列**（例如：插值完成 → 稳定 gap → 策略 ON），而非仅单模式稳态。

7. **全量执行：策略必须跑完**
   - 集成类自测中涉及 RL 策略或运动生成的，**必须**让策略跑完其自然长度（`motion_length_s` 或 ONNX 输出直到动作循环/收敛），不得只跑截断时长（如只跑 4-10s）。
   - 测试时长应优先来自 **ONNX 数据**（metadata 中的时长/帧率，或基于 `time_step` 的周期探测），禁止长期使用写死常量作为唯一依据。
   - 截断执行无法暴露 **历史累积误差**（observation drift、time_step overflow、参考轨迹相位漂移等），这类问题只在长时间运行后才显现。
   - 若策略无显式终止条件（`motion_length_s == 0`），须运行 **≥ 30s**（或根据参考实现确定的合理上界），并在末尾验证稳定性指标。
   - 多次切换测试中，每轮策略执行也须为完整长度，而非缩短到 2s。

8. **分段测试：局部验证优先，全量压轴**
   - 对于**单一机制**的验证（插值效果、PD 增益切换、phase 起步等），可以只跑覆盖该机制的**最短片段**（如插值 2.5s + 稳定 gap 1s），无需跑完整策略，显著节省时间与 token。
   - 典型分段比例：插值/切换验证 ≤ 5s；策略稳定性验证 ≥ 30%（即 `motion_length_s * 0.3`）；phase/终止条件验证须达 100%。
   - 分段测试 PASS 后，至少保留一条**全量压轴测试**（≥ 100% 或跑到 `phase_complete`），确认无长时间漂移。
   - `selftest.py` 中不同阶段的步数应来自配置（如 `get_interpolation_duration()` × `control_hz`），禁止硬编码不随配置变化的常量。

**Agent 提示**：详细清单与反模式见 skill `selftest-reality-alignment`：本仓库 [`.cursor/skills/selftest-reality-alignment/SKILL.md`](.cursor/skills/selftest-reality-alignment/SKILL.md)；若需在所有本机项目中复用，可复制到 `~/.cursor/skills/selftest-reality-alignment/`。

## 适配新网络时的对齐清单（强制）

每次将**新 RL 策略/新 ONNX 模型**接入 UHC 框架时，必须在对应 Policy 类的 `init()` 和 `_build_obs()` 中逐项确认以下内容，并在 selftest 中用 headless 推理覆盖：

### 1. 关节顺序（最高优先级）

| 检查项 | 说明 | 典型错误 |
|--------|------|---------|
| **Policy 关节序 vs 机器人标准序** | 不同网络的关节排列方式不同（如 BeyondMimic 使用 L-R 交替排列），必须在 `init()` 里用 ONNX metadata `joint_names` 建立 `JointMapper`，所有 policy↔robot 之间的数组转换必须走 `JointMapper` | 直接 slice 导致关节值错位 |
| **default_angles 的坐标系** | `default_angles` 若来自 ONNX metadata，则**在 policy 序**；若来自 robot_cfg，则在**机器人标准序**。两者不可混用 | `_ref_joint_pos` 在 policy 序，`self.default_angles[n:]` 在 policy 序 slice，但 `policy_to_robot(_ref)` 已在机器人序，相减结果乱掉 |
| **上肢插值目标的坐标系** | `get_upper_body_target()` 返回的相对偏移必须在**机器人标准序**，且需对 `_ref_joint_pos` 和 `default_angles` **同时** remap 到机器人序后再做差 | 漏 remap default_angles，产生虚假偏移（可高达 ±2 rad） |

```python
# 正确写法：两者都 remap，同序相减
q_robot      = joint_mapper.policy_to_robot(self._ref_joint_pos)
default_robot = joint_mapper.policy_to_robot(self.default_angles)
offset = q_robot[n_lower:] - default_robot[n_lower:]   # ✓ 同序相减
```

### 2. 观测向量的物理帧（速度/角速度）

| 量 | IsaacLab/训练 | MuJoCo `qvel` | 正确做法 |
|----|--------------|---------------|---------|
| `base_lin_vel` | `root_lin_vel_b`（**机体系**） | `qvel[0:3]`（**世界系**） | 用 `quat_rotate_inverse(quat, qvel[0:3])` 转换 |
| `base_ang_vel` | `root_ang_vel_b`（**机体系**） | `qvel[3:6]`（**机体系**，直接可用） | 直接用，无需转换 |
| `projected_gravity` | `quat_rotate_inverse(q, g_world)` | 需手动计算 | `quat_rotate_inverse(quat, [0,0,-1])` |

> **反模式**：凭 C++ 中间层的"直接用"就认为不需要转换——C++ StateEstimator 通常已在 MuJoCo→Pinocchio 接口处完成了世界系→机体系转换，Python 直连 MuJoCo 需要自行处理。

### 3. 动作空间约定

- 确认是 `delta_from_default`（动作 + default = 目标角度）还是 `absolute`（动作直接是目标角度）
- `action_scale` 是**标量**（全局）还是**向量**（逐关节，来自 ONNX metadata）
- `default_angles` 是来自 robot_cfg（机器人标准序）还是 ONNX metadata（policy 序）

### 4. 验证清单（selftest 必查）

```python
# 新策略接入后必须在 selftest 中包含以下检查
r.check("joint_mapper not identity")          # 确认非平凡映射被正确加载
r.check("joint_mapper round-trip")             # policy → robot → policy 误差 < 1e-6
r.check("default_angles shape == num_joints")  # 维度一致
r.check("action scale per-joint or scalar")    # 打印确认
r.check("obs dim matches ONNX input")          # 手动拼接 dim == ONNX input[1]
r.check("kp/kd from metadata not robot_cfg")   # BeyondMimic 类策略有自己的 gains
```

## 2. 提交规范

### Commit 前检查清单

1. `selftest.py` 全量 PASS
2. 无语法错误（`python -m py_compile`）
3. Commit message 说明改了什么、为什么改

### Commit Message 格式

```
<scope>: <简要描述>

<详细说明（可选）>
```

scope 示例：`M0`, `M1`, `config`, `fix`, `selftest`, `docs`

## 3. 人工审核流程

1. Agent 完成功能实现
2. Agent 运行 selftest，确认全部 PASS
3. Agent 提交代码 + selftest 结果
4. Agent 告知人工审核者：可以验证的功能 + 操作步骤
5. 人工审核者做功能验证（产品经理视角）
6. 如有问题，人工审核者只描述现象，Agent 自行 debug

## 4. 项目结构规范

每个项目至少包含：

```
project/
├── scripts/
│   ├── run.py          # 统一入口
│   └── selftest.py     # 自动化测试
├── config/             # 配置文件
├── docs/               # 文档
└── README.md
```

## 5. 环境规范

- 提供 `environment.yml`（conda）或 `requirements.txt`
- 提供 `install.sh` 一键安装脚本
- 可选：`Dockerfile` + `docker_run.sh`

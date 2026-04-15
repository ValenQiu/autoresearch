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

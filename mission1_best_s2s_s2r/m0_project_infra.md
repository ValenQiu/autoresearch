# M0 执行计划：项目基建与环境配置

**Milestone**: M0  
**范围**: 基础设施  
**预估工作量**: 1 天  

## 验收标准

- [ ] 独立项目目录 `universal_humanoid_controller/` 就绪
- [ ] `environment.yml` → `conda env create -f environment.yml` 一键创建环境
- [ ] `install.sh` → 一键安装（conda env + pip 依赖 + 项目本身）
- [ ] `Dockerfile` + `docker_run.sh` → Docker 一键构建启动
- [ ] `uhc/` 包可 `import uhc`
- [ ] 配置加载：`uhc.config.load_profile("sim2sim_loco.yaml")` 返回完整配置字典
- [ ] `python scripts/run.py --profile config/profiles/sim2sim_loco.yaml` 能启动（即使策略未实现，框架不 crash）

## 关键依赖

```yaml
# conda 核心依赖
- python=3.10
- numpy
- scipy
- pyyaml
- mujoco                    # sim2sim backend
- onnxruntime               # ONNX 推理

# pip 依赖
- unitree_sdk2py            # sim2real backend (G1 DDS)
- wandb                     # 模型下载
- pygame                    # Xbox 手柄
- sshkeyboard               # 键盘监听
- termcolor                 # 日志着色
```

## 步骤

1. 在 autoresearch 工作区内创建 `universal_humanoid_controller/` 目录结构
2. 编写 `environment.yml` + `install.sh`
3. 编写 `Dockerfile`（基于 `python:3.10-slim` + mujoco + onnxruntime）
4. 创建 `uhc/` 包骨架（`__init__.py` + 各子模块空文件）
5. 实现配置加载（`uhc/core/config.py`）：分层加载 robot → policy → profile
6. 创建 `scripts/run.py` 入口点骨架
7. 编写 agent skill 文档

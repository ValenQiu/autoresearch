---
name: unitree-g1-documentation-distilled
description: Use when developing, reviewing, or debugging Unitree G1 projects across startup, safety, SDK DDS integration, low-level control, and sim2real deployment migration.
---

# Unitree G1 文档蒸馏（全栈开发版）

## Overview

本 skill 是对 Unitree G1 文档体系的工程化归纳，目标是把“文档知识”转成“可执行检查清单”，覆盖：

- 启动与安全基线
- SDK/DDS 通信
- 低层控制语义
- sim2sim 到 sim2real 迁移
- 本机 mock 到真机切换

## 文档地图（先读顺序）

1. `G1 developer overview`：硬件与开发总览
2. `Quick start`：上电、调试、基础安全流程
3. `Basic services interface`：低层通信主题与消息结构
4. `DDS services interface`：DDS 层接口与服务约定
5. `SDK overview`：SDK 使用入口与模块边界

## 一页蒸馏（关键结论）

### 1) 架构分层

- **策略/编排层**：状态机、策略切换、安全门禁
- **后端适配层**：Mujoco / Unitree SDK
- **通信层**：DDS topic + IDL 消息

目标应始终是：上层逻辑不因 sim/real 切换而改写，仅后端与通信参数变化。

### 2) G1 低层通信最小闭环

- 命令 topic：`rt/lowcmd`
- 状态 topic：`rt/lowstate`
- 常用命令字段：`q/dq/kp/kd/tau`、`level_flag`、`mode_machine`、`mode_pr`
- 常用状态字段：`motor_state[i].q/dq`、`imu quaternion(wxyz)`、`imu gyroscope`、`tick`

### 3) sim2real 网络认知

- 重点是 `interface + domain_id + topic` 一致
- 不是“只改机器人 IP”
- 本机 mock 通常用 `lo`，真机切换用现场网卡（如 `enp2s0`）

### 4) 安全优先级

- 急停路径始终最高优先级
- 通信超时判定必须基于“新帧 freshness”（如 `tick` 变化），不能仅判断对象非空
- 任何自动 fallback 或 e-stop 规则都应与项目策略一致并可观测

## SDK 实施清单（UHC 视角）

1. **配置层**
   - `backend.type: unitree`
   - `state_topic: rt/lowstate`
   - `cmd_topic: rt/lowcmd`
   - `state_timeout_ms` 合理设置（通信 watchdog）

2. **映射层**
   - `joint2motor` 与 `motor2joint` 双向一致
   - `motor2joint=-1` 回退默认角
   - 弱/强电机 mode 与常量值一致

3. **状态层**
   - 关节、IMU、tick 必须完整
   - timeout 基于 freshness（新 tick）而不是缓存对象

4. **验证层**
   - `selftest_real.py`（DDS 契约/超时/映射）
   - `smoke_sim2real.sh preflight`（环境 + 真机路径自测）
   - `selftest.py`（全量回归）

## 本机 mock -> 真机最小切换模板

- 开发期（本机）：
  - `interface: lo`
  - mock bridge 提供 `rt/lowstate`
  - UHC 走 `UnitreeBackend(mock=false)` 验证真机协议语义

- 真机期：
  - `interface: enp2s0`（示例）
  - 保持 topic 和策略配置不变
  - 校验 SDK 版本、domain、一致性

## 典型故障与定位

1. **有进程无动作**
   - 查 topic/domain/interface 是否一致
   - 查 LowCmd 是否真实下发（而非仅构造）

2. **timeout 不触发**
   - 查 freshness 判定逻辑是否只看缓存对象
   - 引入 tick 变化检测

3. **动作错乱/抖动**
   - 查 joint/motor 映射、mode、kp/kd 单位与范围
   - 查仿真和真机控制频率/步长是否匹配

## 快速执行模板

```bash
# 1) 环境 + DDS 契约
python scripts/check_real_env.py
python scripts/selftest_real.py

# 2) 全量回归
python scripts/selftest.py

# 3) 本机 mock / 真机运行
python scripts/run.py --profile config/profiles/sim2real_g1_loco.yaml
```

## 参考链接

- [G1 SDK Development Guide](https://support.unitree.com/home/en/G1_developer)
- [G1 Quick Start](https://support.unitree.com/home/en/G1_developer/quick_start)
- [G1 Basic Services Interface](https://support.unitree.com/home/en/G1_developer/basic_services_interface)
- [G1 DDS Services Interface](https://support.unitree.com/home/en/G1_developer/dds_services_interface)
- [G1 SDK Overview](https://support.unitree.com/home/en/G1_developer/sdk_overview)

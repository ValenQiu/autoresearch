---
name: unitree-g1-sdk-dds-mock
description: Use when implementing or debugging Unitree G1 sim2real communication in UHC, especially LowCmd/LowState DDS mapping, loopback mock bridges, timeout freshness, and migration from local mock (lo) to real NIC (enp2s0).
---

# Unitree G1 SDK DDS 闭环（UHC）

## Overview

本 skill 用于把 UHC 的 `UnitreeBackend` 与 Unitree G1 SDK 的 DDS 语义对齐，并支持本机闭环 mock：

`UHC -> rt/lowcmd -> mock bridge(MuJoCo) -> rt/lowstate -> UHC`

目标是让“策略/状态机不变，仅后端 I/O 适配变化”。

## When to Use

- 新增或修改 `UnitreeBackend` 的 `LowCmd/LowState` 字段映射
- 调试 `state_timeout_ms` 不触发、断流检测失效、旧帧重复
- 需要在无真机条件下验证 sim2real profile 与 DDS 话题协议
- 需要把 loopback(`lo`) 配置切换到真机网卡（如 `enp2s0`）

## 核心接口对齐

- topic：
  - 下发：`rt/lowcmd`
  - 回读：`rt/lowstate`
- 命令字段（最小集）：
  - `motor_cmd[i].q/dq/kp/kd/tau`
  - `level_flag`, `mode_machine`, `mode_pr`
- 状态字段（最小集）：
  - `motor_state[i].q/dq`
  - `imu_state.quaternion`（wxyz）
  - `imu_state.gyroscope`
  - `tick`（用于 freshness）

## 本机闭环 mock 实施模板

1. 启动 mock bridge（订阅 `rt/lowcmd`，驱动 MuJoCo，发布 `rt/lowstate`）
2. UHC profile 使用：
   - `backend.type: unitree`
   - `backend.mode: mock`
   - `backend.domain_id: 1`
   - `backend.interface: lo`
3. 验证：
   - `scripts/smoke_loco_loopback.py`
   - 手工双终端联调（bridge + `scripts/run.py --profile sim2real_g1_loopback.yaml`）

## 真机最小切换

- 不改策略配置、不改 topic
- 仅切换：
  - `backend.interface: lo -> enp2s0`（示例）
  - `backend.domain_id` 按现场 DDS 设置

## 高频坑位

1. **缓存旧帧导致 timeout 失效**  
   - freshness 必须基于“新帧标识”（如 `tick` 变化），不是“对象非空”。

2. **映射不一致**  
   - `joint2motor/motor2joint` 必须双向自洽；
   - `motor2joint=-1` 需回退默认关节角。

3. **网络配置误区**  
   - G1 SDK DDS 重点是 interface/domain/topic；
   - 不是“只改 IP”。

4. **初始化姿态假对齐（看起来像“吊起了”，实际脚仍承重）**  
   - 先算力学：`F_band = k * (||point-root|| - length)`；若 `F_band < mg`，机器人必然贴地。  
   - G1 在本仓默认参数下，`point.z=2.5` 会导致约 `339N`，低于重力（约 `343N`），无法真正悬空。  
   - 与 ASAP 对齐使用 `point=[0,0,3.0]`，并从 XML `qpos0` 起步（不要强注入 standing pose），让四肢在重力下自然下垂。

5. **`i`/`]` 抖动与“乱飞”根因常在控制带宽，而非策略本身**  
   - 高危信号：`INIT` 期间也抖；`loco` 激活后振荡放大。  
   - 常见根因：PD 只在 DDS callback（~50Hz）更新，物理却在 200Hz 跑，导致 `ctrl` 跨 4 个 substep 冻结。  
   - 正确做法：每个 `mj_step` 用最新 `q,dq` 重算  
     `tau = kp*(q_ref-q) + kd*(dq_ref-dq) + tau_ff`，并按 `actuator_ctrlrange` 限幅（与 ASAP / sim2sim 一致）。  
   - 额外注意：按 `]` 时若上肢目标从 0 突跳到 loco reference（如 elbow 0→1rad），会触发饱和；需做 1~2s 插值过渡。

## 验证清单

- [ ] `sim2real` profile 在 `mock=true` 能跑主循环
- [ ] `i` 阶段无明显抖动（INIT 插值可复现）
- [ ] `]` 阶段无突跳（上肢过渡插值生效）
- [ ] bridge 诊断输出包含 root pose + 全关节 q/qdot
- [ ] 断流/旧帧重复能触发预期 timeout 行为
- [ ] loopback 到真机仅改网卡与 domain 即可运行

## 参考链接

- [G1 SDK Development Guide](https://support.unitree.com/home/en/G1_developer)
- [G1 Quick Start](https://support.unitree.com/home/en/G1_developer/quick_start)
- [G1 Basic Services Interface](https://support.unitree.com/home/en/G1_developer/basic_services_interface)
- [G1 DDS Services Interface](https://support.unitree.com/home/en/G1_developer/dds_services_interface)
- [G1 SDK Overview](https://support.unitree.com/home/en/G1_developer/sdk_overview)

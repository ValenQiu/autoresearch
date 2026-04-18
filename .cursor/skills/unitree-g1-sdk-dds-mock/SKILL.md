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
2. UHC 使用 `backend.type: unitree` + `mock: false`
3. `communication.interface: lo`
4. 验证：
   - `scripts/selftest_real.py`
   - `scripts/smoke_sim2real.sh preflight`

## 真机最小切换

- 不改策略配置、不改 topic
- 仅切换：
  - `communication.interface: lo -> enp2s0`（示例）
  - `domain_id` 按现场 DDS 设置

## 高频坑位

1. **缓存旧帧导致 timeout 失效**  
   - freshness 必须基于“新帧标识”（如 `tick` 变化），不是“对象非空”。

2. **映射不一致**  
   - `joint2motor/motor2joint` 必须双向自洽；
   - `motor2joint=-1` 需回退默认关节角。

3. **网络配置误区**  
   - G1 SDK DDS 重点是 interface/domain/topic；
   - 不是“只改 IP”。

## 验证清单

- [ ] `sim2real` profile 在 `mock=true` 能跑主循环
- [ ] `selftest_real.py` 全通过
- [ ] 断流/旧帧重复能触发预期 timeout 行为
- [ ] loopback 到真机仅改网卡与 domain 即可运行

## 参考链接

- [G1 SDK Development Guide](https://support.unitree.com/home/en/G1_developer)
- [G1 Quick Start](https://support.unitree.com/home/en/G1_developer/quick_start)
- [G1 Basic Services Interface](https://support.unitree.com/home/en/G1_developer/basic_services_interface)
- [G1 DDS Services Interface](https://support.unitree.com/home/en/G1_developer/dds_services_interface)
- [G1 SDK Overview](https://support.unitree.com/home/en/G1_developer/sdk_overview)

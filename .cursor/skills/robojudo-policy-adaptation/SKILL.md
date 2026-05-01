---
name: robojudo-policy-adaptation
description: Use when adapting a new ONNX policy (BeyondMimic / ASAP / OmniXtreme / Protomotions / KungfuBot / TWIST) into UHC, debugging "sim2sim works but loopback/real immediately falls", or aligning UHC behavior with the RoboJuDo teacher repo's decoupled Controller/Environment/Policy architecture. Triggers on BM observation layout mismatch, `motion_anchor_pos_b` garbage values, `base_lin_vel` zero-fill OOD, `without_state_estimator`, `override_robot_anchor_pos`, or any "why does RoboJuDo work but we don't" question.
---

# RoboJuDo Policy Adaptation Skill

## When to invoke this skill

Invoke **before**:

1. Adding a new ONNX policy (BeyondMimic / ASAP / OmniXtreme / ProtoMotions / KungfuBot / TWIST / ...).
2. Debugging "sim2sim works, sim2real mock falls / oscillates / diverges".
3. Writing `_build_obs` for any whole-body tracker policy.
4. Designing `UnitreeBackend` / deploy-side body frame estimation.
5. Any conversation where the user says "RoboJuDo can do it, why can't we".

If any of the above, **your first action is to read the distilled reference**:

- [`mission1_best_s2s_s2r/research/robojudo_teacher_distilled.md`](../../mission1_best_s2s_s2r/research/robojudo_teacher_distilled.md)

## Red-flag checklist

If you hit **any** of these, stop and consult the distilled doc:

| Red flag | What it actually means |
|---|---|
| UHC hardcodes `obs = 160` / `obs = 154` etc. | ONNX is self-describing via `observation_names`; hardcoding means you will silently break on WoSE/With-SE switch. |
| `_build_obs` zero-fills `base_lin_vel` / `motion_anchor_pos_b` "because we don't have it" | Training distribution had real values here. You are feeding OOD input. Check if ONNX is WoSE (drop) or With-SE (need override or estimator). |
| `state["base_pos"] is None` branch returns identity | This is the "no state estimator" path. Whole-body trackers will NOT tolerate garbage anchor. Need `override_robot_anchor_pos=True` or WoSE ONNX. |
| Policy code does `isinstance(backend, MujocoBackend)` | Layering violation. All physical state must be backend-agnostic; go through `backend.read_state()` / `backend.get_body_frame()`. |
| You're about to write an ad-hoc state estimator inside the policy | Wrong layer. Estimator belongs in `UnitreeBackend` / `get_body_frame`. Policy stays clean. |
| "It works in sim2sim but not in loopback" argument is closed by "add more interp" | Usually wrong. sim2sim gets ground-truth body frames for free; loopback doesn't. The gap is at the backend layer, not the policy. |
| Hardcoded anchor_body_name | Read `meta["anchor_body_name"]` instead. |

## What RoboJuDo says to do, summarized

1. **Environment / Controller / Policy three-layer decoupling**. No policy code touches MuJoCo API directly.
2. **ONNX metadata drives everything**: `joint_names`, `joint_stiffness/damping`, `action_scale`, `default_joint_pos`, `anchor_body_name`, `body_names`, **`observation_names`**.
3. **WoSE ONNX as default**: training-time removal of `motion_anchor_pos_b` and `base_lin_vel`, so deploy needs no state estimator.
4. **`override_robot_anchor_pos` as tier-2 fallback** when you're stuck with a With-SE ONNX and no estimator: force `motion_anchor_pos_b = 0` in obs; keep rotation real.
5. **Body frames come from backend**, with a clean FK fallback chain (get_body_frame → URDF FK → constant-z+IMU identity). Never from policy-side hacks.
6. **Headless selftest with explicit PASS/FAIL gates**: tilt, |qd|max, pelvis_z, q_target jump. See `scripts/smoke_task_loopback.py`.
7. **`passive → recovery → task` deployment sequence**: bridge boots band-ON, smoke/operator drops band first (SIGUSR1 / `9`), lets the robot crumple on the floor in PASSIVE, then `i`+`]` hands control to BFM-Zero as **recovery** (not as loco-on-a-standing-robot), and only enters task once `tilt<15°` & `max|qd|<1 rad/s` have **held for 2 s**. Anything that assumes "robot already standing at default pose" is wrong for real deployment — see distilled §5.

## Concrete UHC entry points (canonical)

- Policy: `universal_humanoid_controller/uhc/policies/beyondmimic.py`
  - `_build_obs` → metadata-driven segment concat
  - `_compute_anchor_obs` → honors `override_robot_anchor_pos`
  - `_query_anchor_world_frame` → backend-first, FK fallback, identity last-resort
- Backend: `universal_humanoid_controller/uhc/backends/unitree_backend.py`
  - `get_body_frame("pelvis")` → IMU quat + C1 constant-z
  - `get_body_frame("torso_link")` → pelvis + 3-joint waist FK
- Profile: `config/profiles/sim2real_g1_loopback_bfm_bm.yaml`
  - `task_policies[i].override_robot_anchor_pos: true` (loopback/real w/o estimator)
- Bridge GT: `tools/loopback_bridge/run_g1_bridge.py --diagnose-interval-sec N` → prints MuJoCo ground-truth pelvis+torso world pose for cross-check.
- Selftest: `scripts/smoke_task_loopback.py --csv-out out.csv`

## When NOT to use this skill

- Pure sim2sim regression where `MujocoBackend` already has ground-truth body frames; the whole `without_state_estimator` / `override` machinery is a no-op there.
- Non-whole-body policies (locomotion-only with no anchor body concept).
- Hardware-specific issues below the DDS layer (use `unitree-g1-sdk-dds-mock` skill instead).

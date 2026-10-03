# Parameter tuning guide

All parameters live in one YAML file (template:
`config/anytraverse.yaml`), split into an `anytraverse` block and a
`vel_gating` block. The launch file only accepts `ns`, `params_file` and
`init_prompt` — everything else is tuned by editing the YAML. Nested keys
(e.g. `topic.image`) map to dotted ROS parameters (e.g. `topic.image`).

## `anytraverse` block

| Parameter | Type / default | Effect | Tuning advice |
|---|---|---|---|
| `init_prompt` | string, `""` (set via launch, **required**) | Initial prompt→weight map. Syntax `"road: 1.0; bush: -0.8;"`, weights in `[-1, 1]`. | Start with 2–4 prompts covering the dominant surfaces. Positive = traversable, negative = avoid. Refine at runtime via the `human_call` service instead of relaunching. |
| `scene_sim_thresh` | float `[0, 1]`, `0.8` | Reference-scene similarity threshold. A new scene less similar than this triggers `UNKNOWN_SCENE` (`hoc_req=true`). | Lower (e.g. `0.6`) = fewer stops, risks missing novel hazards. Higher (e.g. `0.9`) = stops on small appearance changes. |
| `roi_unc_thresh` | float `[0, 1]`, `0.5` | Mean uncertainty in the region of interest above which the state becomes `UNKNOWN_OBJECT` (`hoc_req=true`). | Lower = more cautious (stops on ambiguous texture). Raise toward `0.7` in visually noisy but safe terrain. |
| `roi_x_bounds` | `[min, max]` in `[0, 1]`, `[0.33, 0.67]` | Horizontal band of the image the ROI covers (0 = left edge). | Narrow to the wheel track (`[0.4, 0.6]`) to ignore irrelevant sides; widen if the robot is wide. Must satisfy `min < max`. |
| `roi_y_bounds` | `[min, max]` in `[0, 1]`, `[0.67, 0.95]` | Vertical band of the ROI (0 = top, 1 = bottom = near field). | Keep in the lower half (ground in front of the robot). Pushing `max` to `1.0` includes the bumper zone; lowering `min` looks further ahead. |
| `hydra_config_file` | path, `config/pipelines/paper.yaml` | Which VLM pipeline to build (relative to workspace root). | See [vlm-pipelines.md](vlm-pipelines.md). Changing this requires a node restart. |
| `topic.image` | string, `/camera/rgb/image_raw` | Camera topic consumed. Absolute → ignores `ns`. | Point at your driver (e.g. `/camera/rgb/image_raw`). Must be `rgb8`-convertible. |
| `topic.trav_map` | string, `trav_map` | Mono8 traversability map output. Relative → follows `ns`. | Remap per consumer if logging multiple robots. |
| `topic.unc_map` | string, `unc_map` | Mono8 uncertainty map output. Relative → follows `ns`. | Same as above. |
| `topic.state` | string, `state` | `State` message output. Relative → follows `ns`. **Must match** `vel_gating.state_topic`. | Keep the two `state` values identical, otherwise gating never sees `hoc_req`. |

## `vel_gating` block

| Parameter | Type / default | Effect | Tuning advice |
|---|---|---|---|
| `enable` | bool, `true` | Gate on `hoc_req`. `false` = node runs but passes velocity through (also settable live via `ros2 param set`). | `false` for mapping/teleop-debug runs; `true` for autonomous runs. |
| `state_topic` | string, `state` | State topic subscribed. **Must match** `anytraverse.topic.state`. | Change only together with the perception side. |
| `cmd_vel_topic.in` | string, `/cmd_vel` | Velocity input (usually the nav stack output). Absolute → ignores `ns`. | Point your planner here; the raw topic is never published onward. |
| `cmd_vel_topic.out` | string, `/cmd_vel_gated` | Gated velocity actually sent to the base. | Point the base driver here, never at the raw topic. |

## Launch arguments

| Argument | Default | Notes |
|---|---|---|
| `ns` | `""` | Namespace for both nodes; relative topics follow it. |
| `params_file` | *(required)* | Path to the YAML described above. |
| `init_prompt` | *(required)* | Overrides the `init_prompt` parameter; same syntax as above. |

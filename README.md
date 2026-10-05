# AnyTraverse ROS

ROS 2 wrapper for [AnyTraverse](https://github.com/AnyTraverse): subscribes to a camera image, publishes mono8
traversability / uncertainty maps plus a `State` message, and gates the
robot's velocity whenever the pipeline requests a human-operator call.

Two nodes, one launch file:

- **`anytraverse`** (`anytraverse_node` executable) — perception.
  Image → `trav_map`, `unc_map`, `state`, plus a `human_call` service.
- **`vel_gating`** (`vel_gating_node` executable) — safety gate.
  Forwards `/cmd_vel` → `/cmd_vel_gated` unchanged unless gating is enabled
  *and* the latest state has `hoc_req=true`, in which case it publishes a
  zero velocity. With `enable=false` the node still runs but purely passes
  velocity through.

All topic names and thresholds are ROS parameters loaded from a single YAML
file; see [docs/parameters.md](docs/parameters.md) for the tuning table and
[docs/vlm-pipelines.md](docs/vlm-pipelines.md) for how to pick the VLM
pipeline. The files under `config/` are templates showing how the
configuration should be structured — copy and adapt them.

## Quickstart

1. **Build** (from the workspace root, inside the pixi environment):

   ```bash
   colcon build --packages-select anytraverse_msgs anytraverse_ros
   source install/setup.bash
   ```

2. **Launch** — `params_file` and `init_prompt` are required; everything
   else comes from the YAML:

   ```bash
   ros2 launch anytraverse_ros anytraverse.launch.py \
     params_file:=$(pwd)/config/anytraverse.yaml \
     init_prompt:="road: 1.0; grass: 0.5; bush: -0.8"
   ```

   `init_prompt` syntax is `<prompt>: <weight>; ...` with weights in
   `[-1, 1]` (positive = traversable, negative = avoid).

3. **Optional overrides:**

   ```bash
   # Run under a namespace (topics like trav_map/state follow it,
   # absolute topics like /cmd_vel and the camera topic do not)
   ros2 launch anytraverse_ros anytraverse.launch.py \
     params_file:=$(pwd)/config/anytraverse.yaml \
     init_prompt:="road: 1.0" \
     ns:=anytraverse # Namespace for topics
   ```

4. **Check it is alive:**

   ```bash
   ros2 topic echo /anytraverse/trav_map --once        # mono8 traversability map
   ros2 topic echo /anytraverse/state --once           # roi + status.hoc_req
   ros2 topic echo /anytraverse/cmd_vel_gated --once   # gated velocity
   ```

5. **Talk to a running pipeline** (no restart needed):

   ```bash
   # Register the current scene as known ("ok" or empty prompt)
   ros2 service call /human_call anytraverse_msgs/srv/HumanCall "{prompt: 'ok'}"
   # Send traversability feedback (updates the prompt weights)
   ros2 service call /human_call anytraverse_msgs/srv/HumanCall "{prompt: 'mud: -1.0'}"
   # Disable gating at runtime (passthrough), re-enable with true
   ros2 param set /vel_gating enable false
   ```

## Switching the VLM pipeline

```bash
# Edit config/anytraverse.yaml:
#   hydra_config_file: config/pipelines/sam3.yaml
```

Available files in `config/pipelines/`: `paper.yaml` (CLIPSeg + CLIP,
as published), `sam3.yaml`, `grounding-sam2.yaml`. Details and the
per-model options (`encoder`, `detector`, `image_size`, `device`) are in
[docs/vlm-pipelines.md](docs/vlm-pipelines.md).

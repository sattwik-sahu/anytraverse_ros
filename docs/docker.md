# Docker usage

Two supported paths share one image (`docker/Dockerfile`) and one
reusable service fragment (`docker/compose.anytraverse.yaml`):

- **A. Direct `docker build` + `docker run`** — quick standalone test of
  this repo on a machine with ROS, Docker, and an NVIDIA GPU.
- **B. `include:` in your own compose file (recommended for integrators)**
  — consume the fragment from a parent/robot compose project and set
  everything via environment variables. No fork or edit of this repo
  required.

The container runs `ros2 launch anytraverse_ros anytraverse.launch.py`
with `params_file:=/ws/config/anytraverse.yaml` plus the `init_prompt`
and `ns` launch arguments resolved from the environment (see
[Environment variables](#environment-variables)). It uses
`network_mode: host`, `ipc: host`, NVIDIA GPU reservation, and
`RMW_IMPLEMENTATION=rmw_zenoh_cpp`.

## A. Direct build and run

From the repo root:

```bash
# Build (ROS_DISTRO defaults to jazzy; humble also supported)
docker build -f docker/Dockerfile -t anytraverse-ros:jazzy .

# One-time weight fetch: allow downloads into a named cache volume
docker run --rm --network host --ipc host --gpus all \
  -e TRANSFORMERS_OFFLINE=0 \
  -e RMW_IMPLEMENTATION=rmw_zenoh_cpp \
  -e INIT_PROMPT="road: 1.0; bush: -0.8" \
  -v $PWD/config:/ws/config:ro \
  -v hf-cache:/ws/.hf-cache \
  anytraverse-ros:jazzy \
  ros2 launch anytraverse_ros anytraverse.launch.py \
    params_file:=/ws/config/anytraverse.yaml \
    "init_prompt:=road: 1.0; bush: -0.8" \
    "ns:="

# Normal offline runs afterwards (equivalent to OFFLINE=1 in Compose)
docker run -d --name anytraverse --network host --ipc host --gpus all \
  -e TRANSFORMERS_OFFLINE=1 \
  -e RMW_IMPLEMENTATION=rmw_zenoh_cpp \
  -v $PWD/config:/ws/config:ro \
  -v hf-cache:/ws/.hf-cache \
  anytraverse-ros:jazzy \
  ros2 launch anytraverse_ros anytraverse.launch.py \
    params_file:=/ws/config/anytraverse.yaml \
    "init_prompt:=road: 1.0; bush: -0.8" \
    "ns:=anytraverse"
```

Notes:

- `-v $PWD/config:/ws/config:ro` mirrors the fragment's `CONFIG_DIR`
  mount: tune `anytraverse.yaml` on the host without rebuilding.
- `-v hf-cache:/ws/.hf-cache` mirrors the fragment's `hf-cache` volume
  (`HF_HOME=/ws/.hf-cache` is baked into the image): VLM weights survive
  container restarts.
- Replace `"ns:=anytraverse"` with `"ns:="` for no namespace, or
  `"ns:=robot1"` for multi-robot setups. See
  [Namespaces](#namespaces-anytraverse_namespace).
- `docker run` has no `${VAR}` interpolation — you expand the values
  yourself, unlike the Compose path below.

## B. Include in your own compose file (recommended)

The fragment is deliberately **not runnable on its own**: it defines the
`anytraverse` service but no `build:` block. The parent project supplies
that, plus the environment:

```yaml
# compose.yaml in YOUR robot project
include:
  - path: path/to/anytraverse_ros/docker/compose.anytraverse.yaml

services:
  anytraverse:
    build:
      context: path/to/anytraverse_ros
      dockerfile: docker/Dockerfile
      args:
        ROS_DISTRO: jazzy
    environment:
      ANYTRAVERSE_NAMESPACE: robot1 # optional, see below
```

Then:

```bash
export CONFIG_DIR=$PWD/config/anytraverse \
       INIT_PROMPT="road: 1.0; bush: -0.8" \
       ANYTRAVERSE_NAMESPACE=robot1
docker compose config | grep -A4 "command:"  # verify ns:=robot1 rendering
docker compose up --build -d
```

Why this shape:

- The fragment is immutable across robots; per-deployment variance comes
  only from env vars. No fork needed to change namespace, prompt, config,
  or offline mode.
- No `container_name` is set in the fragment, so Compose auto-names
  containers (`<project>-anytraverse-1`). Multiple instances (e.g.
  `robot1`, `robot2`) can coexist in one Compose project.
- Keep the fragment filename (`compose.anytraverse.yaml`): it signals a
  reusable fragment. Do not rename it to `docker-compose.yaml` /

  `compose.yaml`, which imply a standalone runnable project.
- Vendor the config: copy this repo's `config/` into your project
  (e.g. `./config/anytraverse`) and point `CONFIG_DIR` at it. Override
  absolute topics there (camera, `cmd_vel`); keep relative outputs
  (`trav_map`, `unc_map`, `state`) short so they follow the namespace.

Verify:

```bash
ros2 node list | grep robot1       # /robot1/anytraverse, /robot1/vel_gating
ros2 topic list | grep robot1      # /robot1/trav_map, /robot1/unc_map, /robot1/state
ros2 topic echo /robot1/state --once
```

## Environment variables

All variance flows through these. In the **Compose path** they are
interpolated by Compose (`${VAR:-default}`) before the container starts;
in the **`docker run` path** you pass the resolved values with `-e` /
explicit CLI args as shown above.

| Variable | Required? / default | Consumed as | Meaning |
|---|---|---|---|
| `INIT_PROMPT` | **Required**, no default | `init_prompt:=` launch arg | Initial traversability prompt. Syntax `"<prompt>: <weight>; ..."` with weights in `[-1, 1]` (positive = traversable, negative = avoid). Example: `"road: 1.0; grass: 0.5; bush: -0.8"`. Missing/empty fails at pipeline startup — set it before `up`. |
| `CONFIG_DIR` | Optional, default `../config` (repo's own `config/`) | Host side of `/ws/config:ro` bind mount | Absolute host path to your `config/` directory (must contain `anytraverse.yaml` + `pipelines/`). Mounted read-only at `/ws/config`, so YAML tuning needs no rebuild. **When using `include:`, always export an absolute path** — the `../config` default only makes sense for local testing of this repo. |
| `ANYTRAVERSE_NAMESPACE` | Optional, default empty (`""` = no namespace) | `ns:=` launch arg | ROS namespace for both nodes (`anytraverse`, `vel_gating`). See [Namespaces](#namespaces-anytraverse_namespace). |
| `OFFLINE` | Optional, default `1` | `TRANSFORMERS_OFFLINE` container env | `1` = transformers runs fully offline, cache-only. `0` = allow downloads. Run once with `OFFLINE=0` to fetch VLM weights into the `hf-cache` volume, then omit it (back to `1`) afterwards. |

Fixed inside the fragment/image (not configurable, listed so integrators
are not surprised):

| Setting | Value | Notes |
|---|---|---|
| `HF_HOME` | `/ws/.hf-cache` | Baked into the image and the fragment env; persisted via the `hf-cache` named volume. |
| `RMW_IMPLEMENTATION` | `rmw_zenoh_cpp` | Set in the fragment env; match it in your other services / host shell. |
| `params_file` | `/ws/config/anytraverse.yaml` | Always the mounted config; edit the host `CONFIG_DIR` copy to tune. |

## Namespaces (`ANYTRAVERSE_NAMESPACE`)

The launch file already namespaces both nodes
(`namespace=LaunchConfiguration("ns")`). The fragment maps
`ANYTRAVERSE_NAMESPACE` → `ns:=`:

- Unset/empty → `ns:=` → today's behavior: nodes `/anytraverse`,
  `/vel_gating`; topics `/trav_map`, `/state`, `/cmd_vel_gated`.
- `ANYTRAVERSE_NAMESPACE=anytraverse` → nodes
  `/anytraverse/anytraverse`, `/anytraverse/vel_gating`; outputs
  `/anytraverse/trav_map`, `/anytraverse/unc_map`,
  `/anytraverse/state`; service `/anytraverse/human_call`. Node-name ==
  namespace is legal ROS 2, just looks redundant.
- `ANYTRAVERSE_NAMESPACE=robot1` → everything above under `/robot1/*`.

ROS resolution rules apply unchanged:

- **Relative** names follow the namespace: `trav_map`, `unc_map`,
  `state`, `human_call`. Keep them relative in your `CONFIG_DIR` copy.
- **Absolute** names ignore it: `/camera/rgb/image_raw`, `/cmd_vel`,
  `/cmd_vel_gated`. To namespace inputs/outputs on a multi-robot setup,
  point them at robot-scoped absolutes in your vendored
  `anytraverse.yaml` (e.g. `topic.image: /robot1/camera/rgb/image_raw`,
  `cmd_vel_topic.in: /robot1/cmd_vel`, `cmd_vel_topic.out:
  /robot1/cmd_vel_gated`).
- Keep `anytraverse.topic.state` and `vel_gating.state_topic` identical
  (both relative `"state"` by default) — otherwise gating never sees
  `hoc_req`. Namespacing preserves this automatically since both resolve
  under the same `ns`.

With a namespace set, qualify your CLI calls:

```bash
ros2 topic echo /robot1/trav_map --once
ros2 topic echo /robot1/state --once
ros2 service call /robot1/human_call anytraverse_msgs/srv/HumanCall "{prompt: 'ok'}"
ros2 param set /robot1/vel_gating enable false
```

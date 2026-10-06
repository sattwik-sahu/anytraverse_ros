# syntax=docker/dockerfile:1
#
# AnyTraverse ROS — multi-stage production image.
#
#   Stage `build`:   resolves the locked pixi environment for ${ROS_DISTRO},
#                    builds the colcon workspace, and bakes the entrypoint.
#   Stage `production`: minimal runtime image — pixi env + built workspace +
#                    entrypoint. No toolchain, no manifests, no build cache.
#
# Build examples:
#   docker build -f docker/Dockerfile -t anytraverse-ros:jazzy .
#   docker build -f docker/Dockerfile --build-arg ROS_DISTRO=humble \
#       -t anytraverse-ros:humble .
#
# Notes:
#   * Package caches are persisted across builds with BuildKit cache mounts
#     (see the `pixi install` step). They never enter image layers. Prune
#     with `docker builder prune` if builder disk runs low.
#   * Only pixi.toml/pixi.lock are copied before `pixi install`, so the
#     expensive environment layer is invalidated solely by dependency
#     changes, not by source edits.
#   * Both stages use WORKDIR /ws so colcon's absolute paths and
#     --symlink-install links stay valid in the production image.

ARG ROS_DISTRO=jazzy

# ==== BUILD ====

FROM ghcr.io/prefix-dev/pixi:0.81.0 AS build

# Re-declare: an ARG from before the first FROM is out of scope inside a
# stage unless re-declared (otherwise ${ROS_DISTRO} expands to "").
ARG ROS_DISTRO=jazzy

WORKDIR /ws

# Copy manifests first so the environment layer below is cached
# independently of source changes. .dockerignore (context root) keeps the
# context lean; it must stay at the repo root — Docker reads it from the
# build-context root, not from docker/.
COPY pixi.toml pixi.lock ./

# Pin cache locations explicitly so the mounts below target exactly what
# pixi, rattler (conda packages), and uv (PyPI wheels) use.
ENV PIXI_CACHE_DIR=/root/.cache/pixi \
    RATTLER_CACHE_DIR=/root/.cache/rattler \
    UV_CACHE_DIR=/root/.cache/uv

RUN --mount=type=cache,id=anytraverse-pixi,target=/root/.cache/pixi,sharing=locked \
    --mount=type=cache,id=anytraverse-rattler,target=/root/.cache/rattler,sharing=locked \
    --mount=type=cache,id=anytraverse-uv,target=/root/.cache/uv,sharing=locked \
    pixi install --locked -e "${ROS_DISTRO}"

# Now the full source tree, then the workspace build. Runs in the ROS
# environment (the default pixi env has no ROS packages, so -e is required).
COPY . .
RUN pixi run -e "${ROS_DISTRO}" build

# Bake the entrypoint: pixi env vars + activation (incl. install/setup.bash,
# which exists by now) + exec delegation. Generated after the build so the
# workspace setup is captured; keep all entrypoint assembly in this one layer.
RUN pixi shell-hook -e "${ROS_DISTRO}" -s bash > /shell-hook && \
    { echo '#!/bin/bash'; cat /shell-hook; echo 'exec "$@"'; } > /ws/entrypoint.sh && \
    chmod 0755 /ws/entrypoint.sh

# ==== PRODUCTION ====

FROM ubuntu:24.04 AS production

# Same re-declaration needed here for the COPY path below.
ARG ROS_DISTRO=jazzy

WORKDIR /ws

# Fixed HuggingFace cache location inside the image. Mount a persistent
# volume here (see docker/compose.anytraverse.yaml) so VLM weights
# survive container restarts.
ENV HF_HOME=/ws/.hf-cache

COPY --from=build /ws/.pixi/envs/${ROS_DISTRO} /ws/.pixi/envs/${ROS_DISTRO}
COPY --from=build --chmod=0755 /ws/entrypoint.sh /ws/entrypoint.sh
COPY --from=build /ws/install /ws/install
COPY --from=build /ws/build /ws/build
COPY --from=build /ws/log /ws/log

# Runtime sources for --symlink-install links. Kept after the install copy
# so source edits don't invalidate the environment layers above.
COPY ./src /ws/src

ENTRYPOINT ["/ws/entrypoint.sh"]

CMD ["bash"]

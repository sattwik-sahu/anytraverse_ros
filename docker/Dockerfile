FROM ghcr.io/prefix-dev/pixi:0.81.0 AS build

# Re-declare: an ARG from before the first FROM is out of scope inside
# stages unless re-declared (otherwise ${ROS_DISTRO} expands to "").
ARG ROS_DISTRO=jazzy

WORKDIR /ws
COPY . .

RUN pixi install --locked -e ${ROS_DISTRO}
RUN pixi run -e ${ROS_DISTRO} build

RUN pixi shell-hook -e ${ROS_DISTRO} -s bash > /shell-hook
RUN echo "#!/bin/bash" > /ws/entrypoint.sh
RUN cat /shell-hook >> /ws/entrypoint.sh

RUN echo 'exec "$@"' >> /ws/entrypoint.sh

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

COPY ./src /ws/src

ENTRYPOINT [ "/ws/entrypoint.sh" ]

CMD [ "bash" ]

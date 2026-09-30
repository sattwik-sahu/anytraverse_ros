ARG ROS_DISTRO=jazzy

FROM ghcr.io/prefix-dev/pixi:0.81.0 AS build

WORKDIR /ws
COPY . .

RUN pixi install --locked -e ${ROS_DISTRO}

RUN pixi shell-hook -e ${ROS_DISTRO} -s bash > /shell-hook
RUN echo "#!/bin/bash" > /ws/entrypoint.sh
RUN cat /shell-hook >> /ws/entrypoint.sh

RUN echo 'exec "$@"' >> /ws/entrypoint.sh

FROM ubuntu:24.04 AS production

WORKDIR /ws

COPY --from=build /ws/.pixi/envs/${ROS_DISTRO} /ws/.pixi/envs/${ROS_DISTRO}
COPY --from=build --chmod=0755 /ws/entrypoint.sh /ws/entrypoint.sh

COPY ./src /ws/src

ENTRYPOINT [ "/ws/entrypoint.sh" ]

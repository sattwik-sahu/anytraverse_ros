import rclpy
from geometry_msgs.msg import Twist
from rcl_interfaces.msg import ParameterDescriptor, SetParametersResult
from rclpy.node import Node
from rclpy.parameter import Parameter

from anytraverse_msgs.msg import State

from anytraverse_ros.constants import (
    STATE_TOPIC,
    VEL_GATING_ENABLE,
    VEL_GATING_NODE_NAME,
    VEL_IN_TOPIC,
    VEL_OUT_TOPIC,
    create_vel_qos_profile,
)


class AnyTraverseVelocityGatingNode(Node):
    """Gate command velocity on the AnyTraverse ``hoc_req`` flag.

    Subscribes to a velocity input topic and the AnyTraverse state topic.
    Publishes the input velocity unchanged unless gating is enabled and
    the latest state requests a human-operator call, in which case a
    zero velocity is published.

    When ``enable`` is false the node still runs but purely passes
    velocity through.

    All topic names are ROS parameters (no remappings needed).
    """

    def __init__(self) -> None:
        super().__init__(node_name=VEL_GATING_NODE_NAME)

        self._hoc_req: bool = False

        self.declare_parameters(
            namespace="",
            parameters=[
                (
                    "enable",
                    VEL_GATING_ENABLE,
                    ParameterDescriptor(
                        description="Whether to activate velocity gating. "
                        "When false the node passes velocity through."
                    ),
                ),
                (
                    "state_topic",
                    STATE_TOPIC,
                    ParameterDescriptor(description="The name of the state topic"),
                ),
                (
                    "cmd_vel_topic.in",
                    VEL_IN_TOPIC,
                    ParameterDescriptor(
                        description="The name of the input velocity topic"
                    ),
                ),
                (
                    "cmd_vel_topic.out",
                    VEL_OUT_TOPIC,
                    ParameterDescriptor(
                        description="The name of the gated output velocity topic"
                    ),
                ),
            ],
        )

        vel_in_topic: str = (
            self.get_parameter("cmd_vel_topic.in").get_parameter_value().string_value
        )
        state_topic: str = (
            self.get_parameter("state_topic").get_parameter_value().string_value
        )
        vel_out_topic: str = (
            self.get_parameter("cmd_vel_topic.out").get_parameter_value().string_value
        )

        self._enable: bool = (
            self.get_parameter("enable").get_parameter_value().bool_value
        )
        self.add_on_set_parameters_callback(self._on_set_params_callback)

        self.get_logger().info(f"Enable gating: {self._enable}")
        self.get_logger().info(f"State topic: {state_topic}")
        self.get_logger().info(f"Vel in topic: {vel_in_topic}")
        self.get_logger().info(f"Vel out topic: {vel_out_topic}")

        # Create topics
        self._vel_in = self.create_subscription(
            msg_type=Twist,
            topic=vel_in_topic,
            qos_profile=create_vel_qos_profile(),
            callback=self._vel_callback,
        )
        self._state = self.create_subscription(
            msg_type=State,
            topic=state_topic,
            qos_profile=create_vel_qos_profile(),
            callback=self._state_callback,
        )
        self._vel_out = self.create_publisher(
            msg_type=Twist,
            topic=vel_out_topic,
            qos_profile=create_vel_qos_profile(),
        )

    def _on_set_params_callback(
        self, params: list[Parameter]
    ) -> SetParametersResult:
        """Cache the ``enable`` flag on runtime parameter changes."""
        for param in params:
            if param.name == "enable":
                if param.type_ != Parameter.Type.BOOL:
                    return SetParametersResult(
                        successful=False, reason="enable must be a bool"
                    )
                self._enable = bool(param.value)
        return SetParametersResult(successful=True)

    def _state_callback(self, msg: State) -> None:
        self._hoc_req = bool(msg.status.hoc_req)

    def _vel_callback(self, msg: Twist) -> None:
        # Disabled -> pure passthrough. Enabled -> gate on hoc_req.
        if not self._enable or not self._hoc_req:
            self._vel_out.publish(msg)
        else:
            self._vel_out.publish(Twist())


def main(args=None):
    rclpy.init(args=args)
    vel_gating_node = AnyTraverseVelocityGatingNode()

    try:
        rclpy.spin(node=vel_gating_node)
    except KeyboardInterrupt:
        pass
    finally:
        vel_gating_node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

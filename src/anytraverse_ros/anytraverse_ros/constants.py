"""Shared constants for the AnyTraverse ROS 2 nodes.

Topics are configured via ROS parameters (see ``params.py`` and the
velocity gating node); the values below are the defaults used when no
parameter is provided. Absolute defaults (leading ``/``) ignore
namespaces; relative defaults stay under the node namespace.
QoS is split per direction: sensor-data for the image subscription,
reliable for map/state publishers.
"""

from typing import Final

from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

NODE_NAME: Final[str] = "anytraverse"
VEL_GATING_NODE_NAME: Final[str] = "vel_gating"

# Defaults match the launch file defaults so `ros2 run` without
# parameters behaves the same as `ros2 launch` with defaults.
IMAGE_TOPIC: Final[str] = "/camera/rgb/image_raw"
TRAV_MAP_TOPIC: Final[str] = "trav_map"
UNC_MAP_TOPIC: Final[str] = "unc_map"
STATE_TOPIC: Final[str] = "state"

VEL_GATING_ENABLE: Final[bool] = True
VEL_IN_TOPIC: Final[str] = "/cmd_vel"
VEL_OUT_TOPIC: Final[str] = "/cmd_vel_gated"

HUMAN_CALL_SERVICE: Final[str] = "human_call"

IMAGE_ENCODING: Final[str] = "mono8"

IMAGE_QOS_DEPTH: Final[int] = 5
MAP_QOS_DEPTH: Final[int] = 1
STATE_QOS_DEPTH: Final[int] = 10
VEL_QOS_DEPTH: Final[int] = 10


def create_image_qos_profile() -> QoSProfile:
    """Create the QoS profile for the image subscription.

    Matches typical camera drivers (BEST_EFFORT sensor data, depth 5).

    Returns:
        QoSProfile: Best-effort, keep-last sensor-data-like profile.
    """
    return QoSProfile(
        depth=IMAGE_QOS_DEPTH,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        history=QoSHistoryPolicy.KEEP_LAST,
    )


def create_map_qos_profile() -> QoSProfile:
    """Create the QoS profile for traversability/uncertainty map publishers.

    Returns:
        QoSProfile: Reliable, keep-last depth-1 profile.
    """
    return QoSProfile(
        depth=MAP_QOS_DEPTH,
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
    )


def create_state_qos_profile() -> QoSProfile:
    """Create the QoS profile for the state publisher.

    Returns:
        QoSProfile: Reliable, keep-last depth-10 profile.
    """
    return QoSProfile(
        depth=STATE_QOS_DEPTH,
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
    )


def create_vel_qos_profile() -> QoSProfile:
    """Create the QoS profile for velocity gating comms.

    Used for the velocity input subscription, the state subscription,
    and the gated velocity publisher: reliable, keep-last depth-10,
    matching the state publisher so no state updates are missed.

    Returns:
        QoSProfile: Reliable, keep-last depth-10 profile.
    """
    return QoSProfile(
        depth=VEL_QOS_DEPTH,
        reliability=QoSReliabilityPolicy.RELIABLE,
        history=QoSHistoryPolicy.KEEP_LAST,
    )

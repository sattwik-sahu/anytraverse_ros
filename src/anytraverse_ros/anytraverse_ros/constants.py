"""Shared constants for the AnyTraverse ROS 2 node.

Topics are relative so namespaces/remaps work under Docker Compose.
QoS is split per direction: sensor-data for the image subscription,
reliable for map/state publishers.
"""

from typing import Final

from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy

NODE_NAME: Final[str] = "anytraverse_node"

# Relative so ``ros2 launch ... image_topic:=/camera/rgb/image_raw``
# remaps cleanly under namespaces and Docker Compose.
IMAGE_TOPIC: Final[str] = "image_raw"
TRAV_MAP_TOPIC: Final[str] = "trav_map"
UNC_MAP_TOPIC: Final[str] = "unc_map"
STATE_TOPIC: Final[str] = "state"

HUMAN_CALL_SERVICE: Final[str] = "human_call"

IMAGE_ENCODING: Final[str] = "mono8"

IMAGE_QOS_DEPTH: Final[int] = 5
MAP_QOS_DEPTH: Final[int] = 1
STATE_QOS_DEPTH: Final[int] = 10


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

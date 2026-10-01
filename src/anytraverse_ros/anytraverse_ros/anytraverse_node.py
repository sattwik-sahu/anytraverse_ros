"""AnyTraverse ROS 2 node entry point.

Decoupled perception: subscribes to an image, publishes mono8
traversability/uncertainty maps plus a header-stamped state message.
"""

from __future__ import annotations

import threading
import time
from threading import Thread
from typing import Any, Optional, Tuple

import numpy.typing as npt
import rclpy
import torch
from anytraverse.state import TraversalState
from cv_bridge import CvBridge
from hydra.utils import instantiate
from numpy import uint8
from omegaconf import OmegaConf
from PIL import Image as PILImage
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.service import Service
from rclpy.subscription import Subscription
from sensor_msgs.msg import Image
from std_msgs.msg import Header

from anytraverse_msgs.msg import Roi, State, Status, TravPref
from anytraverse_msgs.srv import HumanCall

from anytraverse_ros.constants import (
    HUMAN_CALL_SERVICE,
    IMAGE_ENCODING,
    IMAGE_TOPIC,
    NODE_NAME,
    STATE_TOPIC,
    TRAV_MAP_TOPIC,
    UNC_MAP_TOPIC,
    create_image_qos_profile,
    create_map_qos_profile,
    create_state_qos_profile,
)
from anytraverse_ros.image_utils import tensor_to_mono8
from anytraverse_ros.params import declare_anytraverse_params, load_anytraverse_params

_TRAV_STATE_TO_MSG = {
    TraversalState.OK: Status.OK,
    TraversalState.UNKNOWN_OBJECT: Status.UNKNOWN_OBJECT,
    TraversalState.UNKNOWN_SCENE: Status.UNKNOWN_SCENE,
}


class AnyTraverseNode(Node):
    """ROS 2 wrapper around the AnyTraverse traversability pipeline.

    Subscribes to a raw RGB image topic, runs the pipeline in a background
    worker thread (latest-frame-only), and publishes mono8 traversability
    and uncertainty maps plus a header-stamped state message. A
    ``human_call`` service exposes operator feedback to the pipeline.

    Attributes:
        _anytraverse: The instantiated AnyTraverse pipeline.
        _bridge: ROS/OpenCV image converter.
        _image_sub: Subscription to the raw image topic.
        _trav_map_pub: Publisher for the mono8 traversability map.
        _unc_map_pub: Publisher for the mono8 uncertainty map.
        _state_pub: Publisher for the ROI/state message.
        _human_call_srv: Service for human operator input.
        _latest_msg: Latest buffered ``(image, header)`` pair, or None.
        _busy: Whether an inference worker thread is running.
        _lock: Guards ``_latest_msg`` and ``_busy``.
        _pipe_lock: Guards pipeline ``step()`` vs service callbacks.
    """

    def __init__(self) -> None:
        """Initialize subscriptions, publishers, buffers, and the pipeline."""
        super().__init__(node_name=NODE_NAME)

        # Build the AnyTraverse pipeline
        self.get_logger().info("Building AnyTraverse pipeline")
        self._anytraverse: Any = None
        self._build_anytraverse_pipeline()

        # CV bridge
        self._bridge: CvBridge = CvBridge()

        # Subscribe to the image topic (sensor-data QoS to match drivers)
        self._image_sub: Subscription[Image] = self.create_subscription(
            msg_type=Image,
            topic=IMAGE_TOPIC,
            qos_profile=create_image_qos_profile(),
            callback=self._image_callback,
        )

        # Publishers for the AnyTraverse output topics (reliable QoS so
        # decoupled consumers and rosbag do not miss state transitions)
        self._trav_map_pub: Publisher[Image] = self.create_publisher(
            msg_type=Image,
            topic=TRAV_MAP_TOPIC,
            qos_profile=create_map_qos_profile(),
        )
        self._unc_map_pub: Publisher[Image] = self.create_publisher(
            msg_type=Image,
            topic=UNC_MAP_TOPIC,
            qos_profile=create_map_qos_profile(),
        )
        self._state_pub: Publisher[State] = self.create_publisher(
            msg_type=State,
            topic=STATE_TOPIC,
            qos_profile=create_state_qos_profile(),
        )

        # Image message buffer for performance boost
        self._latest_msg: Optional[Tuple[npt.NDArray[uint8], Header]] = None
        self._busy: bool = False
        self._lock: threading.Lock = threading.Lock()
        # Guards the AnyTraverse pipeline: step() runs in the worker
        # thread while human_call()/register_scene() run in the
        # executor thread via the human_call service.
        self._pipe_lock: threading.RLock = threading.RLock()

        # Lightweight runtime counters (logged periodically, no new topics)
        self._frames_received: int = 0
        self._frames_dropped: int = 0
        self._inference_count: int = 0

        # Human operator input service
        self._human_call_srv: Service[HumanCall] = self.create_service(
            HumanCall, HUMAN_CALL_SERVICE, self._handle_human_call
        )

    def _build_anytraverse_pipeline(self) -> None:
        """Declare parameters, load them, and instantiate the pipeline.

        Raises:
            FileNotFoundError: If the Hydra configuration file does not exist.
            ValueError: If ROI bounds parameters are invalid.
        """
        # Declare parameters
        declare_anytraverse_params(self)

        # Read the parameters
        params = load_anytraverse_params(self)

        # Log values for debugging
        self.get_logger().info(f"Init prompts: {params.init_prompt}")
        self.get_logger().info(
            f"Scene similarity threshold: {params.ref_scene_similarity_threshold}"
        )
        self.get_logger().info(
            f"ROI uncertainty threshold: {params.roi_uncertainty_threshold}"
        )
        self.get_logger().info(f"ROI X bounds: {params.roi_x_bounds}")
        self.get_logger().info(f"ROI Y bounds: {params.roi_y_bounds}")

        # Build the pipeline using the parameters
        if not params.hydra_config_file.exists():
            raise FileNotFoundError(
                f"Hydra configuration file does not exist at {params.hydra_config_file.as_posix()}"
            )
        else:
            cfg = OmegaConf.load(params.hydra_config_file)
            self.get_logger().info(
                f"Loaded hydra config:\n{OmegaConf.to_container(cfg)}"
            )
            build_anytraverse_pipeline = instantiate(cfg)
            self._anytraverse = build_anytraverse_pipeline(
                init_traversability_preferences=params.init_prompt,
                ref_scene_similarity_threshold=params.ref_scene_similarity_threshold,
                roi_uncertainty_threshold=params.roi_uncertainty_threshold,
                roi_x_bounds=params.roi_x_bounds,
                roi_y_bounds=params.roi_y_bounds,
            )

    def _image_callback(self, msg: Image) -> None:
        """Buffer the latest image and ensure a worker thread is running.

        Latest-frame-only policy: overwrites any unprocessed frame so the
        worker always processes the freshest image. Overwritten frames are
        counted as dropped.

        Args:
            msg: Incoming ROS image message.
        """
        img = self._bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")

        with self._lock:
            self._frames_received += 1
            if self._busy and self._latest_msg is not None:
                self._frames_dropped += 1
            self._latest_msg = (img, msg.header)
            should_start = not self._busy
            if should_start:
                self._busy = True

        if should_start:
            Thread(target=self._inference_worker, daemon=True).start()

    def _inference_worker(self) -> None:
        """Drain the image buffer, running inference and publishing results.

        Runs until the buffer is empty. Inference and publish failures are
        logged and skipped without killing the worker.
        """
        try:
            while True:
                with self._lock:
                    if self._latest_msg is None:
                        self._busy = False
                        return  # No more frames to process

                    img, header = self._latest_msg
                    self._latest_msg = None

                # --- RUN INFERENCE ---
                try:
                    start = time.monotonic()
                    with self._pipe_lock:
                        with torch.inference_mode():
                            output = self._anytraverse.step(PILImage.fromarray(img))
                    inference_ms = (time.monotonic() - start) * 1000.0
                except Exception as exc:
                    self.get_logger().error(f"Inference failed: {exc}")
                    continue

                # --- PUBLISH ---
                try:
                    self._publish(
                        trav_map=output.traversability_map,
                        unc_map=output.uncertainty_map,
                        roi_trav=output.roi_traversability,
                        roi_unc=output.roi_uncertainty,
                        trav_state=output.traversal_state,
                        hoc_req=output.traversal_state is not TraversalState.OK,
                        incoming_header=header,
                    )
                    self._inference_count += 1
                    if self._inference_count % 50 == 0:
                        self.get_logger().info(
                            f"Inference {self._inference_count}: "
                            f"{inference_ms:.1f} ms, "
                            f"received={self._frames_received} "
                            f"dropped={self._frames_dropped}"
                        )
                except Exception as exc:
                    self.get_logger().error(f"Publish failed: {exc}")
        finally:
            with self._lock:
                self._busy = False

    def _preferences_to_ros(self) -> list[TravPref]:
        """Snapshot pipeline preferences as ROS messages.

        Returns:
            List of ``TravPref`` messages, one per prompt/weight pair.
        """
        with self._pipe_lock:
            prefs_snapshot = dict(self._anytraverse.traversability_preferences)
        prefs: list[TravPref] = []
        for prompt, weight in prefs_snapshot.items():
            pref_msg = TravPref()
            pref_msg.prompt = prompt
            pref_msg.trav = float(weight)
            prefs.append(pref_msg)
        return prefs

    def _handle_human_call(
        self, request: HumanCall.Request, response: HumanCall.Response
    ) -> HumanCall.Response:
        """Handle a human operator service call.

        An empty prompt or ``"ok"`` registers the current scene; any other
        prompt is forwarded as human feedback.

        Args:
            request: Service request carrying the operator prompt.
            response: Service response to populate with current preferences.

        Returns:
            The populated service response with success flag and message.
        """
        prompt = request.prompt.strip()
        try:
            with self._pipe_lock:
                if not prompt or prompt.lower() == "ok":
                    self._anytraverse.register_scene()
                    message = "Scene registered"
                else:
                    self._anytraverse.human_call(human_input=prompt)
                    message = "Human feedback applied"
        except (ValueError, RuntimeError) as exc:
            self.get_logger().warning(f"Invalid human operator call: {exc}")
            response.success = False
            response.message = f"Invalid human operator call: {exc}"
            response.prefs = []
            return response

        response.success = True
        response.message = message
        response.prefs = self._preferences_to_ros()
        return response

    def _publish(
        self,
        trav_map: torch.Tensor,
        unc_map: torch.Tensor,
        roi_trav: float,
        roi_unc: float,
        trav_state: TraversalState,
        hoc_req: bool,
        incoming_header: Header,
    ) -> None:
        """Convert pipeline output to ROS messages and publish them.

        Args:
            trav_map: Traversability map tensor ([0, 1]).
            unc_map: Uncertainty map tensor ([0, 1]).
            roi_trav: ROI traversability scalar.
            roi_unc: ROI uncertainty scalar.
            trav_state: Traversal state enum from the pipeline.
            hoc_req: Whether human-operator call is requested.
            incoming_header: Header copied from the triggering image.
        """
        # Convert traversability and uncertainty maps to mono8
        trav_np = tensor_to_mono8(trav_map)
        unc_np = tensor_to_mono8(unc_map)

        # Publish as mono8 images with the triggering image header
        trav_map_msg = self._bridge.cv2_to_imgmsg(trav_np, encoding=IMAGE_ENCODING)
        unc_map_msg = self._bridge.cv2_to_imgmsg(unc_np, encoding=IMAGE_ENCODING)
        trav_map_msg.header = incoming_header
        unc_map_msg.header = incoming_header

        # Publish maps
        self._trav_map_pub.publish(trav_map_msg)
        self._unc_map_pub.publish(unc_map_msg)

        # State msg (stamped so decoupled consumers can time-sync)
        state_msg = State()
        state_msg.header = incoming_header

        # ROI specific statistics
        roi_msg = Roi()
        roi_msg.traversability = roi_trav
        roi_msg.uncertainty = roi_unc

        # Status with enum code plus human-readable label
        status_msg = Status()
        status_msg.state = _TRAV_STATE_TO_MSG[trav_state]
        status_msg.traversal_state = trav_state.name
        status_msg.hoc_req = hoc_req

        # Build the state msg
        state_msg.roi = roi_msg
        state_msg.status = status_msg
        state_msg.trav_prefs = self._preferences_to_ros()

        # Publish the state msg
        self._state_pub.publish(msg=state_msg)


def main() -> None:
    """Initialize ROS, spin the node, and shut down cleanly."""
    rclpy.init()
    node = AnyTraverseNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

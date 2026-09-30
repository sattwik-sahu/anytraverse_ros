import threading
from pathlib import Path
from threading import Thread

import cv2
import rclpy
import torch
from anytraverse.preferences import parse_trav_pref_syntax
from anytraverse.state import TraversalState
from cv_bridge import CvBridge
from hydra.utils import instantiate
from omegaconf import OmegaConf
from PIL import Image as PILImage
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, QoSReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Header

from anytraverse_msgs.msg import Roi, State, Status, TravPref
from anytraverse_msgs.srv import HumanCall


class AnyTraverseNode(Node):
    """The AnyTraverse node."""

    def __init__(self) -> None:
        super().__init__(node_name="anytraverse_node")

        # Fast QoS
        qos_profile = QoSProfile(
            depth=1,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
        )

        # Build the AnyTraverse pipeline
        self.get_logger().info("Building AnyTraverse pipeline")
        self._build_anytraverse_pipeline()

        # CV bridge
        self._bridge = CvBridge()

        # Subscribe to the image topic
        self._image_sub = self.create_subscription(
            msg_type=Image,
            topic="/camera/rgb/image_raw",
            qos_profile=qos_profile,
            callback=self._image_callback,
        )

        # Publishers for the AnyTraverse output topics
        self._trav_map_pub = self.create_publisher(
            msg_type=Image,
            topic="trav_map",
            qos_profile=qos_profile,
        )
        self._unc_map_pub = self.create_publisher(
            msg_type=Image,
            topic="unc_map",
            qos_profile=qos_profile,
        )
        self._state_pub = self.create_publisher(
            msg_type=State, topic="state", qos_profile=qos_profile
        )

        # Image message buffer for performance boost
        self._latest_msg = None
        self._busy = False
        self._lock = threading.Lock()
        # Guards the AnyTraverse pipeline: step() runs in the worker
        # thread while human_call()/register_scene() run in the
        # executor thread via the human_call service.
        self._pipe_lock = threading.RLock()

        # Human operator input service
        self._human_call_srv = self.create_service(
            HumanCall, "human_call", self._handle_human_call
        )

    def _build_anytraverse_pipeline(self) -> None:
        # Declare parameters
        self.declare_parameters(
            namespace="",
            parameters=[
                ("init_prompt", ""),
                ("roi_unc_thresh", 0.0),
                ("scene_sim_thresh", 0.0),
                ("roi_x_bounds", [0.33, 0.67]),
                ("roi_y_bounds", [0.75, 0.95]),
                ("hydra_config_file", ""),
            ],  # type: ignore
        )

        # Read the parameters
        init_prompt = parse_trav_pref_syntax(
            syntax=self.get_parameter(name="init_prompt")
            .get_parameter_value()
            .string_value
        )
        ref_scene_sim_thresh = (
            self.get_parameter(name="scene_sim_thresh")
            .get_parameter_value()
            .double_value
        )
        roi_unc_thresh = (
            self.get_parameter(name="roi_unc_thresh").get_parameter_value().double_value
        )
        roi_x_bounds: tuple[float, float] = tuple(
            self.get_parameter(name="roi_x_bounds")
            .get_parameter_value()
            .double_array_value.tolist()
        )
        roi_y_bounds: tuple[float, float] = tuple(
            self.get_parameter(name="roi_y_bounds")
            .get_parameter_value()
            .double_array_value.tolist()
        )
        hydra_config_file: Path = Path(
            self.get_parameter("hydra_config_file").get_parameter_value().string_value
        )

        # Log values for debugging
        self.get_logger().info(f"Init prompts: {init_prompt}")
        self.get_logger().info(f"Scene similarity threshold: {ref_scene_sim_thresh}")
        self.get_logger().info(f"ROI uncertainty threshold: {roi_unc_thresh}")
        self.get_logger().info(f"ROI X bounds: {roi_x_bounds}")
        self.get_logger().info(f"ROI Y bounds: {roi_y_bounds}")

        # Build the pipeline using the parameters
        if not hydra_config_file.exists():
            raise FileNotFoundError(
                f"Hydra configuration file does not exist at {hydra_config_file.as_posix()}"
            )
        else:
            cfg = OmegaConf.load(hydra_config_file)
            self.get_logger().info(
                f"Loaded hydra config:\n{OmegaConf.to_container(cfg)}"
            )
            build_anytraverse_pipeline = instantiate(cfg)
            self._anytraverse = build_anytraverse_pipeline(
                init_traversability_preferences=init_prompt,
                ref_scene_similarity_threshold=ref_scene_sim_thresh,
                roi_uncertainty_threshold=roi_unc_thresh,
                roi_x_bounds=roi_x_bounds,
                roi_y_bounds=roi_y_bounds,
            )

    def _image_callback(self, msg):
        img = self._bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")

        with self._lock:
            self._latest_msg = (img, msg.header)
            should_start = not self._busy
            if should_start:
                self._busy = True

        if should_start:
            Thread(target=self._inference_worker, daemon=True).start()

    def _inference_worker(self):
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
                    with self._pipe_lock:
                        with torch.inference_mode():
                            output = self._anytraverse.step(PILImage.fromarray(img))
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
                        trav_state=output.traversal_state.name,
                        hoc_req=output.traversal_state is not TraversalState.OK,
                        incoming_header=header,
                    )
                except Exception as exc:
                    self.get_logger().error(f"Publish failed: {exc}")
        finally:
            with self._lock:
                self._busy = False

    def _preferences_to_ros(self) -> list[TravPref]:
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
    ):
        prompt = request.prompt.strip()
        try:
            with self._pipe_lock:
                if not prompt or prompt.lower() == "ok":
                    self._anytraverse.register_scene()
                else:
                    self._anytraverse.human_call(human_input=prompt)
        except (ValueError, RuntimeError) as exc:
            self.get_logger().warning(f"Invalid human operator call: {exc}")
            response.prefs = []
            return response

        response.prefs = self._preferences_to_ros()
        return response

    def _publish(
        self,
        trav_map: torch.Tensor,
        unc_map: torch.Tensor,
        roi_trav: float,
        roi_unc: float,
        trav_state: str,
        hoc_req: bool,
        incoming_header: Header,
    ) -> None:
        def _to_uint8_img(t):
            img = t.detach().cpu().numpy()
            if img.ndim == 2:
                img = (img * 255).clip(0, 255).astype("uint8")
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
            elif img.ndim == 3 and img.shape[0] in (1, 3):
                img = img.transpose(1, 2, 0)
                img = (img * 255).clip(0, 255).astype("uint8")
            else:
                img = (img * 255).clip(0, 255).astype("uint8")
            return img

        # Convert traversability and uncertainty maps to numpy
        trav_np = _to_uint8_img(trav_map)
        unc_np = _to_uint8_img(unc_map)

        # Compress the traversability and uncertainty maps
        trav_map_msg = self._bridge.cv2_to_imgmsg(trav_np, encoding="rgb8")
        unc_map_msg = self._bridge.cv2_to_imgmsg(unc_np, encoding="rgb8")
        trav_map_msg.header = incoming_header
        unc_map_msg.header = incoming_header

        # Publish maps
        self._trav_map_pub.publish(trav_map_msg)
        self._unc_map_pub.publish(unc_map_msg)

        # State msg
        state_msg = State()

        # ROI specific statistics
        roi_msg = Roi()
        roi_msg.traversability = roi_trav
        roi_msg.uncertainty = roi_unc

        # Status
        status_msg = Status()
        status_msg.traversal_state = trav_state
        status_msg.hoc_req = hoc_req

        # Build the state msg
        state_msg.roi = roi_msg
        state_msg.status = status_msg
        state_msg.trav_prefs = self._preferences_to_ros()

        # Publish the state msg
        self._state_pub.publish(msg=state_msg)


def main():
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

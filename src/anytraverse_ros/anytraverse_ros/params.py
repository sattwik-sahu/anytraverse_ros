"""Parameter declaration and loading for the AnyTraverse node."""

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from anytraverse.preferences import parse_trav_pref_syntax
from rclpy.node import Node
from rcl_interfaces.msg import FloatingPointRange, ParameterDescriptor

DEFAULT_INIT_PROMPT: str = ""
DEFAULT_ROI_UNC_THRESH: float = 0.0
DEFAULT_SCENE_SIM_THRESH: float = 0.0
DEFAULT_ROI_X_BOUNDS: Tuple[float, float] = (0.33, 0.67)
DEFAULT_ROI_Y_BOUNDS: Tuple[float, float] = (0.75, 0.95)
DEFAULT_HYDRA_CONFIG_FILE: str = ""


@dataclass(frozen=True)
class AnyTraverseParams:
    """Resolved AnyTraverse pipeline parameters.

    Attributes:
        init_prompt: Parsed initial traversability preferences.
        ref_scene_similarity_threshold: Reference scene similarity threshold.
        roi_uncertainty_threshold: ROI uncertainty threshold.
        roi_x_bounds: Normalized (min, max) ROI bounds on the x-axis.
        roi_y_bounds: Normalized (min, max) ROI bounds on the y-axis.
        hydra_config_file: Path to the Hydra pipeline config file.
    """

    init_prompt: dict
    ref_scene_similarity_threshold: float
    roi_uncertainty_threshold: float
    roi_x_bounds: Tuple[float, float]
    roi_y_bounds: Tuple[float, float]
    hydra_config_file: Path


def _float_descriptor(description: str) -> ParameterDescriptor:
    """Build a [0, 1] float parameter descriptor.

    Args:
        description: Human-readable parameter description.

    Returns:
        ParameterDescriptor with a [0, 1] floating-point range.
    """
    return ParameterDescriptor(
        description=description,
        floating_point_range=[
            FloatingPointRange(from_value=0.0, to_value=1.0, step=0.01)
        ],
    )


def declare_anytraverse_params(node: Node) -> None:
    """Declare the AnyTraverse ROS parameters with original defaults.

    Args:
        node: Node on which to declare the parameters.
    """
    node.declare_parameter(
        "init_prompt",
        DEFAULT_INIT_PROMPT,
        ParameterDescriptor(description="Initial traversability prompt syntax."),
    )
    node.declare_parameter(
        "roi_unc_thresh",
        DEFAULT_ROI_UNC_THRESH,
        _float_descriptor("ROI uncertainty threshold in [0, 1]."),
    )
    node.declare_parameter(
        "scene_sim_thresh",
        DEFAULT_SCENE_SIM_THRESH,
        _float_descriptor("Reference scene similarity threshold in [0, 1]."),
    )
    node.declare_parameter(
        "roi_x_bounds",
        list(DEFAULT_ROI_X_BOUNDS),
        ParameterDescriptor(description="Normalized ROI x bounds [min, max]."),
    )
    node.declare_parameter(
        "roi_y_bounds",
        list(DEFAULT_ROI_Y_BOUNDS),
        ParameterDescriptor(description="Normalized ROI y bounds [min, max]."),
    )
    node.declare_parameter(
        "hydra_config_file",
        DEFAULT_HYDRA_CONFIG_FILE,
        ParameterDescriptor(description="Path to the Hydra pipeline config file."),
    )


def _validate_bounds(name: str, bounds: Tuple[float, float]) -> None:
    """Validate a normalized ROI bound pair.

    Args:
        name: Parameter name for error messages.
        bounds: (min, max) bound pair.

    Raises:
        ValueError: If bounds are out of [0, 1] or min >= max.
    """
    if len(bounds) != 2:
        raise ValueError(f"{name} must have exactly 2 elements, got {bounds}")
    lo, hi = float(bounds[0]), float(bounds[1])
    if not (0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0):
        raise ValueError(f"{name} must be within [0, 1], got {bounds}")
    if not lo < hi:
        raise ValueError(f"{name} requires min < max, got {bounds}")


def load_anytraverse_params(node: Node) -> AnyTraverseParams:
    """Read and parse the declared AnyTraverse parameters.

    Args:
        node: Node holding the declared parameters.

    Returns:
        AnyTraverseParams: Resolved and parsed parameter values.

    Raises:
        ValueError: If ROI bounds are invalid.
    """
    init_prompt = parse_trav_pref_syntax(
        syntax=node.get_parameter(name="init_prompt")
        .get_parameter_value()
        .string_value
    )
    ref_scene_sim_thresh = (
        node.get_parameter(name="scene_sim_thresh").get_parameter_value().double_value
    )
    roi_unc_thresh = (
        node.get_parameter(name="roi_unc_thresh").get_parameter_value().double_value
    )
    roi_x_bounds: Tuple[float, float] = tuple(
        node.get_parameter(name="roi_x_bounds")
        .get_parameter_value()
        .double_array_value.tolist()
    )
    roi_y_bounds: Tuple[float, float] = tuple(
        node.get_parameter(name="roi_y_bounds")
        .get_parameter_value()
        .double_array_value.tolist()
    )
    _validate_bounds("roi_x_bounds", roi_x_bounds)
    _validate_bounds("roi_y_bounds", roi_y_bounds)
    hydra_config_file: Path = Path(
        node.get_parameter("hydra_config_file").get_parameter_value().string_value
    )
    return AnyTraverseParams(
        init_prompt=init_prompt,
        ref_scene_similarity_threshold=ref_scene_sim_thresh,
        roi_uncertainty_threshold=roi_unc_thresh,
        roi_x_bounds=roi_x_bounds,
        roi_y_bounds=roi_y_bounds,
        hydra_config_file=hydra_config_file,
    )

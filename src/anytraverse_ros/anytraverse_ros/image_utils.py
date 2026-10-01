"""Image conversion helpers for the AnyTraverse node.

Pure functions with no ROS dependency so they stay unit-testable.
"""

import numpy as np
import numpy.typing as npt
import torch


def tensor_to_mono8(t: torch.Tensor) -> npt.NDArray[np.uint8]:
    """Convert a traversability/uncertainty tensor to a mono8 image.

    The pipeline conceptually produces single-channel ``[0, 1]`` maps, but
    defensive handling covers multi-channel or scalar tensors.

    Args:
        t: Input tensor. ``HxW`` is scaled directly; ``CxHxW`` is reduced
            across the channel dim by mean; 0-d scalars become ``1x1``.

    Returns:
        HxW uint8 mono8 image array.
    """
    arr = t.detach().cpu().float().numpy()
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=0.0)
    if arr.ndim == 0:
        arr = arr.reshape(1, 1)
    elif arr.ndim == 3:
        # Channel-first CxHxW of any C: mean across channels.
        arr = arr.mean(axis=0)
    elif arr.ndim > 3:
        # Unexpected rank: mean over all leading dims, keep last two.
        arr = arr.reshape(-1, arr.shape[-2], arr.shape[-1]).mean(axis=0)
    img = (arr * 255.0).clip(0, 255).astype(np.uint8)
    return img


# Backwards-compatible alias (mono8-only output).
tensor_to_uint8_rgb = tensor_to_mono8

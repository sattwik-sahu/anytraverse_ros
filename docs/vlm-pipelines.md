# Configuring the VLM pipeline (Hydra)

The perception node does not hardcode any vision model. At startup it loads
a Hydra config file (selected by the `hydra_config_file` parameter),
instantiates it with `hydra.utils.instantiate`, and calls the resulting
partial with the pipeline arguments (`init_traversability_preferences`,
`ref_scene_similarity_threshold`, `roi_uncertainty_threshold`,
`roi_x_bounds`, `roi_y_bounds`).

The files under `config/` are templates showing how the configuration
should be structured: `config/anytraverse.yaml` for ROS parameters and
`config/pipelines/*.yaml` for the Hydra pipeline configs. Copy them and
adapt — do not point the node at package internals.

## Config template rules

Every file in `config/pipelines/` must be a Hydra **partial** targeting one
of the builders in `anytraverse.presets` (anytraverse `2.0.0`):

```yaml
_target_: anytraverse.build_pipeline_sam3
_partial_: true
# ... only model-level options below (encoder, detector, image_size,
# device, dtype). NEVER the five node-supplied arguments listed above.
```

Consequences:

- `_partial_: true` is mandatory — without it Hydra calls the builder
  immediately (missing the node-supplied arguments) and startup crashes.
- Only set keys that are real arguments of the chosen builder. Unknown keys
  raise at instantiate time.
- `device` / `dtype`: leave `null` for auto-detect unless you have a reason
  (e.g. `device: cpu` for debugging). `dtype` is a `torch.dtype` object,
  which is awkward to express in YAML — leave it `null`.

## Available pipelines

| File | Builder | Attention (VLM) | Scene encoder | When to use |
|---|---|---|---|---|
| `paper.yaml` | `build_pipeline_from_paper` | CLIPSeg | CLIP ViT-B/32 | Default; reproduces the paper; lightest. |
| `sam3.yaml` | `build_pipeline_sam3` | SAM 3 | `encoder` option: `clip` / `siglip2` (default, best) / `dinov2` | Sharper prompt masks; `image_size: 560` on low-memory GPUs. |
| `grounding-sam2.yaml` | `build_pipeline_grounded_sam2` | Grounding DINO or OWLv2 boxes → SAM 2 masks | `encoder` as above | Cluttered scenes with distinct objects; `detector: owlv2` as an alternative to `grounding-dino`. |

## Switching pipelines

1. Edit `config/anytraverse.yaml`:

   ```yaml
   hydra_config_file: config/pipelines/sam3.yaml
   ```

   (Path is resolved relative to the process working directory — launch
   from the workspace root, as in the README quickstart.)
2. Optionally tune the model-level options inside the chosen
   `config/pipelines/*.yaml` (see the comments at the top of each file).
3. Restart the `anytraverse` node (the pipeline is built once at startup;
   `ros2 param set` cannot swap it).

## Writing a custom pipeline config

To add e.g. `config/pipelines/my-pipeline.yaml`:

1. Pick a builder from `anytraverse.presets` and check its signature for
   settable options.
2. Follow the template: `_target_`, `_partial_: true`, then only
   model-level keys.
3. Point `hydra_config_file` at it and restart.

Example (SAM 3 with the lightweight CLIP encoder and low-res mode):

```yaml
_target_: anytraverse.build_pipeline_sam3
_partial_: true
encoder: clip
image_size: 560
device: null
dtype: null
```

# A850v2 compute texture-size corruption

With DD-Turnip v0.3.4, DroidDeck's original LSFG 2x shaders produced alternating
normal and black frames, sometimes with fragments of the image in the top-left
corner. The workaround replaces a narrowly scoped compute texture-size query
with the existing bindless image-size lowering.

## Isolation

In the affected compute path, copying with integer-coordinate `texelFetch`
worked. Sampling with `textureLod` using coordinates divided by
`textureSize(input, 0)` reproduced the corruption. Replacing the queried size
with the known dimensions (1562 x 720) made that sampling path work.

A diagnostic encoding the integer dimensions into color bits showed that
`textureSize` returned incorrect, workgroup-dependent values, whereas
`imageSize` returned the expected dimensions. This implicates the GETSIZE query
path; it is not just a floating-point reciprocal or LSFG precision issue.
The underlying hardware/driver cause of the incorrect GETSIZE result is not
established by this test.

## Workaround scope

The Android patch applies only to chip ID `0x44051431` (A850v2), compute shaders,
non-array 2D textures, two 32-bit result components, an already lowered bindless
texture handle, and a constant LOD of zero. It preserves descriptor validity
and non-uniform access flags.

For this case, RESINFO reads the width and height already encoded for the
view's base mip. It does not perform GETSIZE's LOD minification, so the rewrite
must not be extended to nonzero or dynamic LODs. Array, cube, 3D, multisample
queries, other shader stages, and other chip IDs keep their original path.
The recipe enables this only for Android, the platform tested here.

## Manual diagnostic

[`a850-compute-texture-size.comp`](a850-compute-texture-size.comp) is the small
GLSL probe used during diagnosis, with a guard added to clear the partial
final column instead of shifting by 32. It is a shader, not a standalone Vulkan
test runner. To run it in a compute harness:

1. Create a 1562 x 720 sampled 2D image and an equally sized RGBA8 storage image,
   each with a non-array 2D view. Bind a sampler at set 0/binding 1, the sampled
   image at binding 3, and the output storage image at binding 8.
2. Compile as a Vulkan compute shader, for example with
   `glslangValidator -V a850-compute-texture-size.comp -o query.spv`.
3. Transition the images appropriately and dispatch 98 x 45 x 1 workgroups
   (local size 16 x 16). Make compute storage writes visible before reading
   back or displaying the output.
4. Each 48-pixel column encodes one bit, least significant bit first. Red
   represents width, green height, and blue is always one. The top half uses
   `textureSize`, the bottom half `imageSize`. Both halves should encode
   width 1562 (bits 1, 3, 4, 9, 10) and height 720 (bits 4, 6, 7, 9).
   Pixels at x >= 1536 are blue padding.

The observed failure and success below were obtained in DroidDeck's compute
pipeline with these bindings. Reproduction in a separate harness has not
been verified; pipeline and descriptor state may matter.

## Recorded validation

- Device: Xiaomi M154FF, SM8975, Adreno 850v2 (`0x44051431`), Android 17/API 37.
- Application: DroidDeck 0.6.0 (`e9e0186`, runtime r9); original LSFG FP16, 2x.
- Baseline: DD-Turnip v0.3.4, Mesa
  `e2ab6687d5ad700cc2b856af684aa014f9dae943`, recipe
  `de8bba431f1c8dd96b61c403262cf74f7756ef19`.
- Build: official Android patch set plus this workaround, NDK r26d,
  Android API 34 target, platform SDK 36. No experimental descriptor-cache
  patch was included.
- Before: diagnostic top half had incorrect dimensions; bottom half correctly
  encoded 1562 x 720. After: both halves consistently encoded 1562 x 720.
- Restored the original LSFG shaders and actual 2x generation after diagnosis.
  In the subsequent 32-frame capture, the prior black corruption was absent;
  the device user also confirmed normal rendering.
- Tested library SHA-256:
  `c5475d61a53063c18b7eddcd535a1a2f191081269264d4578af1957a74febc4c`.
  The submitted patch adds an explanatory comment to the tested code; its
  executable logic is identical.

This is targeted application/device validation, not Vulkan CTS coverage.
Other GPUs, Linux, null descriptors, and nonzero view base mips have not been
tested on hardware. A separate application setting (adaptive target 60 FPS)
improved perceived input latency; that is not a driver performance result or
part of this patch.

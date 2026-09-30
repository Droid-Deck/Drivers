# DroidDeck Turnip Drivers

Turnip (Mesa freedreno Vulkan) for DroidDeck. Every build fetches the latest Mesa main, applies the patch set in
`patches/`, and builds two drivers from that one Mesa commit: an Android driver (Adrenotools-style) and a Linux
ARM64 driver. Both ship in one bundle per release.

## Bundle

Each release publishes `DD-Turnip-vX.Y.Z.zip` and its `.sha256`:

```
manifest.json
android/libvulkan_freedreno.so
android/meta.json
linux/libvulkan_freedreno.so
linux/meta.json
```

| Path | Driver |
|---|---|
| `android/` | Android, bionic libc, NDK r26d, KGSL. `meta.json` is the Adrenotools format, so the directory loads as-is. |
| `linux/` | Linux ARM64, glibc, KGSL + MSM, Wayland/X11 WSI. `meta.json` records platform, libc, Mesa commit and library SHA-256. |

`manifest.json` indexes both drivers, so a loader picks one by platform:

```json
{
  "schemaVersion": 1,
  "package": "DD-Turnip",
  "version": "0.1.0",
  "tag": "DD-Turnip-v0.1.0",
  "mesa": { "version": "26.3.0-devel", "commit": "…", "source": "https://gitlab.freedesktop.org/mesa/mesa" },
  "drivers": {
    "android": { "path": "android", "library": "android/libvulkan_freedreno.so", "meta": "android/meta.json", "architecture": "aarch64", "libc": "bionic", "sha256": "…" },
    "linux":   { "path": "linux",   "library": "linux/libvulkan_freedreno.so",   "meta": "linux/meta.json",   "architecture": "aarch64", "libc": "glibc",  "sha256": "…" }
  }
}
```

Packaging refuses a bundle unless both libraries are AArch64, link the right libc, carry their platform markers
(IMapper5 gralloc on Android, Wayland and XCB WSI on Linux) and the PWR_MAX patch, and were built from the
same Mesa commit.

## Patch set

`patches/series.json` lists every patch in order, with its targets and a summary. The same file drives the
build and the release notes.

| Patch | Android | Linux |
|---|:-:|:-:|
| `scripts/gralloc_ubwc_detect.py` | ✓ | |
| `scripts/fix_a8xx_dev_info.py` | ✓ | ✓ |
| `scripts/apply_a8xx_gpus.py` | ✓ | ✓ |
| `scripts/apply_a7xx_gen1_quirks.py` | ✓ | ✓ |
| `scripts/apply_a7xx_gen2_ubwc_hint.py` | ✓ | ✓ |
| `scripts/add_aimapper_gralloc.py` + `aimapper/u_gralloc_aimapper.c` | ✓ | |
| `scripts/add_ubwc_swapchain_usage.py` | ✓ | |
| `scripts/autotune_bandwidth.py` | ✓ | ✓ |
| `scripts/perf_pwr_max.py` | ✓ | ✓ |
| `scripts/android_ndk_compat.py` | ✓ | |
| `scripts/linux_kgsl_wsi.py` | | ✓ |
| `linux/0001` … `linux/0006` (mesh shaders, half-wave subgroups, A8XX cube, bindless and IB fixes) | | ✓ |

A script whose anchor no longer matches Mesa main exits non-zero and a `.patch` that no longer applies fails
`git apply`, so upstream drift fails the build instead of shipping a driver without the fix. The `Check`
workflow applies the whole set to the current Mesa main on every push.

The RedMagic UBWC swapchain and IMapper5 gralloc work is by [Leb-Sun](https://github.com/Leb-Sun).

## Versioning

Tags are `DD-Turnip-vX.Y.Z`. The next version comes from the highest published (non-draft, non-prerelease)
`DD-Turnip-v*` release:

| Trigger | Rule | Examples |
|---|---|---|
| No release yet | `0.1.0` | → `0.1.0` |
| Weekly schedule, or manual run without Hotfix | minor + 1, patch reset; minor 9 rolls into the next major | `0.1.0` → `0.2.0`, `0.1.5` → `0.2.0`, `0.9.0` → `1.0.0`, `1.9.3` → `2.0.0` |
| Manual run with Hotfix | patch + 1 | `0.1.0` → `0.1.1` → `0.1.2`, `0.9.0` → `0.9.1` |

## Release notes

- `0.1.0` lists the Turnip, Vulkan runtime and gralloc commits merged into Mesa main in the 30 days up to the
  build commit.
- Later releases read the previous release's Mesa commit from its notes and list every upstream commit between
  the two builds, with the Turnip, Vulkan runtime and gralloc commits called out and a GitLab compare link.
- Every release lists the patches applied, per target.

## Workflows

- `release.yml` runs every Wednesday 12:00 UTC and on manual dispatch (`Hotfix` checkbox). It resolves the
  version and the Mesa main commit, builds Android and Linux in parallel from that commit, packages and verifies
  the bundle, and publishes the release.
- `check.yml` runs the version tests and applies the patch set to Mesa main on every push and pull request.

```sh
gh workflow run release.yml
gh workflow run release.yml -f hotfix=true
```

## Local build

```sh
./build.sh 0.1.0
```

Fetches Mesa main (`MESA_REF` selects another ref), builds both drivers under `work/` and writes
`dist/DD-Turnip-v0.1.0.zip`. Requirements: meson ≥ 1.5, ninja, Python with mako and PyYAML, flex, bison,
`ANDROID_NDK_HOME` pointing at an Android NDK, and `aarch64-linux-gnu-gcc`/`g++`/binutils with a host
`wayland-scanner` for the Linux cross build. The Linux sysroot is assembled from Ubuntu 24.04 arm64 packages
without root (`scripts/linux_sysroot.sh`); set `LINUX_SYSROOT` to reuse one.

## License

GPL-3.0, see `LICENSE`.

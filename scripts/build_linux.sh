#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mesa=$(cd "$1" && pwd)
sysroot="${LINUX_SYSROOT:-$root/work/sysroot}"
work="$root/work/linux"
out="$root/out/linux"
[[ -d "$sysroot/usr/include" ]] || "$root/scripts/linux_sysroot.sh" "$sysroot"
sysroot=$(cd "$sysroot" && pwd)
rm -rf "$work" "$out"
mkdir -p "$work" "$out"
git -c advice.detachedHead=false clone -q --shared "$mesa" "$work/mesa"
python3 "$root/scripts/apply_patches.py" linux "$work/mesa" 2>&1 | tee "$work/patch.log"

cat > "$work/cross.ini" <<INI
[binaries]
c = 'aarch64-linux-gnu-gcc'
cpp = 'aarch64-linux-gnu-g++'
ar = 'aarch64-linux-gnu-ar'
strip = 'aarch64-linux-gnu-strip'
pkg-config = 'pkg-config'
wayland-scanner = '$(command -v wayland-scanner)'

[properties]
sys_root = '$sysroot'
pkg_config_libdir = '$sysroot/usr/lib/aarch64-linux-gnu/pkgconfig:$sysroot/usr/share/pkgconfig'

[built-in options]
c_args = ['--sysroot=$sysroot']
cpp_args = ['--sysroot=$sysroot']
c_link_args = ['--sysroot=$sysroot']
cpp_link_args = ['--sysroot=$sysroot']

[host_machine]
system = 'linux'
cpu_family = 'aarch64'
cpu = 'aarch64'
endian = 'little'
INI

meson setup "$work/build" "$work/mesa" --cross-file "$work/cross.ini" --buildtype release \
  -Dvulkan-drivers=freedreno -Dfreedreno-kmds=msm,kgsl -Dgallium-drivers= -Dplatforms=wayland,x11 \
  -Dopengl=false -Dgbm=disabled -Dglx=disabled -Degl=disabled -Dllvm=disabled -Dvulkan-layers= \
  -Dtools= -Dvideo-codecs= -Dxmlconfig=disabled
ninja -C "$work/build" -j "${BUILD_JOBS:-$(nproc)}" src/freedreno/vulkan/libvulkan_freedreno.so
aarch64-linux-gnu-strip -o "$out/libvulkan_freedreno.so" "$work/build/src/freedreno/vulkan/libvulkan_freedreno.so"
git -C "$work/mesa" rev-parse HEAD > "$out/mesa-commit"

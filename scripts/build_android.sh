#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mesa=$(cd "$1" && pwd)
ndk="${ANDROID_NDK_HOME:?set ANDROID_NDK_HOME to an Android NDK}/toolchains/llvm/prebuilt/linux-x86_64/bin"
api=34
work="$root/work/android"
out="$root/out/android"
rm -rf "$work" "$out"
mkdir -p "$work" "$out"
git -c advice.detachedHead=false clone -q --shared "$mesa" "$work/mesa"
python3 "$root/scripts/apply_patches.py" android "$work/mesa" 2>&1 | tee "$work/patch.log"

cat > "$work/cross.ini" <<INI
[binaries]
ar = '$ndk/llvm-ar'
c = ['$ndk/aarch64-linux-android$api-clang']
cpp = ['$ndk/aarch64-linux-android$api-clang++', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '--start-no-unused-arguments', '-static-libstdc++', '--end-no-unused-arguments']
c_ld = '$ndk/ld.lld'
cpp_ld = '$ndk/ld.lld'
strip = '$ndk/llvm-strip'
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$ndk/pkg-config', '/usr/bin/pkg-config']

[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'armv8'
endian = 'little'
INI

cat > "$work/native.ini" <<INI
[binaries]
c = '$ndk/clang'
cpp = '$ndk/clang++'
ar = '$ndk/llvm-ar'
strip = '$ndk/llvm-strip'
c_ld = '$ndk/ld.lld'
cpp_ld = '$ndk/ld.lld'
INI

flags="-D__ANDROID__ -Wno-error -Wno-deprecated-declarations -Wno-incompatible-pointer-types-discards-qualifiers -Wno-incompatible-pointer-types"
CFLAGS="$flags" CXXFLAGS="$flags" meson setup "$work/build" "$work/mesa" \
  --cross-file "$work/cross.ini" --native-file "$work/native.ini" --prefix "$work/install" \
  -Dbuildtype=release -Dstrip=true -Dplatforms=android -Dplatform-sdk-version=36 -Dandroid-stub=true \
  -Dandroid-libbacktrace=disabled -Dgallium-drivers= -Dvulkan-drivers=freedreno -Dvulkan-beta=true \
  -Dfreedreno-kmds=kgsl -Degl=disabled -Dvideo-codecs=
ninja -C "$work/build" -j "${BUILD_JOBS:-$(nproc)}" install
cp "$work/install/lib/libvulkan_freedreno.so" "$out/"
git -C "$work/mesa" rev-parse HEAD > "$out/mesa-commit"

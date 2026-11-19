#!/usr/bin/env bash
# Build PocketTurnip (Mesa Turnip, Adreno 740 / Galaxy S23) as an
# AdrenoTools-compatible zip.
#
# Env:
#   MESA_REF     Mesa tag/branch to build (default: mesa-26.3.1)
#   DEFAULT_FPS  Built-in frame cap, 0 = off (default: 0)
#   NDK_DIR      Existing NDK path (downloaded if unset)
#   MESA_DIR     Existing Mesa checkout (cloned if unset)
#   OUT_DIR      Where the zip goes (default: ./out)
set -euo pipefail

MESA_REF="${MESA_REF:-mesa-26.3.1}"
DEFAULT_FPS="${DEFAULT_FPS:-0}"
NDK_VER="r27c"
SDK_VER=31
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-$ROOT/work}"
OUT_DIR="${OUT_DIR:-$ROOT/out}"
mkdir -p "$WORK" "$OUT_DIR"

if [ -z "${NDK_DIR:-}" ]; then
  NDK_DIR="$WORK/android-ndk-$NDK_VER"
  if [ ! -d "$NDK_DIR" ]; then
    echo "== Downloading NDK $NDK_VER"
    curl -sSLo "$WORK/ndk.zip" "https://dl.google.com/android/repository/android-ndk-$NDK_VER-linux.zip"
    unzip -q "$WORK/ndk.zip" -d "$WORK" && rm "$WORK/ndk.zip"
  fi
fi

if [ -z "${MESA_DIR:-}" ]; then
  MESA_DIR="$WORK/mesa"
  rm -rf "$MESA_DIR"
  echo "== Cloning Mesa $MESA_REF"
  git clone --depth 1 -b "$MESA_REF" https://gitlab.freedesktop.org/mesa/mesa.git "$MESA_DIR"
fi

echo "== Applying PocketTurnip patches"
python3 "$ROOT/scripts/apply_patches.py" "$MESA_DIR" "$DEFAULT_FPS"

TC="$NDK_DIR/toolchains/llvm/prebuilt/linux-x86_64/bin"
CROSS="$WORK/android-aarch64.ini"
cat > "$CROSS" <<EOF
[binaries]
ar = '$TC/llvm-ar'
c = ['$TC/aarch64-linux-android$SDK_VER-clang']
cpp = ['$TC/aarch64-linux-android$SDK_VER-clang++', '-fno-exceptions', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-static-libstdc++']
c_ld = 'lld'
cpp_ld = 'lld'
strip = '$TC/llvm-strip'
pkg-config = ['env', 'PKG_CONFIG_LIBDIR=$WORK/pkgconfig', '/usr/bin/pkg-config']

[host_machine]
system = 'android'
cpu_family = 'aarch64'
cpu = 'cortex-a715'
endian = 'little'
EOF
mkdir -p "$WORK/pkgconfig"

BUILD="$WORK/build"
rm -rf "$BUILD"
echo "== Configuring"
# -mcpu: Snapdragon 8 Gen 2 = Cortex-X3 / A715 / A710 / A510 (armv9-a);
# cortex-a715 tuning is safe on all of its cores.
meson setup "$BUILD" "$MESA_DIR" \
  --cross-file "$CROSS" \
  -Dbuildtype=release \
  -Dc_args="-mcpu=cortex-a715" -Dcpp_args="-mcpu=cortex-a715 -Wno-c++11-narrowing" \
  -Dplatforms=android \
  -Dplatform-sdk-version=$SDK_VER \
  -Dandroid-stub=true \
  -Dgallium-drivers= \
  -Dvulkan-drivers=freedreno \
  -Dvulkan-beta=true \
  -Degl=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled -Dglx=disabled -Dgbm=disabled \
  -Dfreedreno-kmds=kgsl \
  -Dstrip=true

echo "== Building"
ninja -C "$BUILD" src/freedreno/vulkan/libvulkan_freedreno.so

echo "== Packaging"
PKG="$WORK/pkg"
rm -rf "$PKG" && mkdir -p "$PKG"
cp "$BUILD/src/freedreno/vulkan/libvulkan_freedreno.so" "$PKG/"
patchelf --set-soname vulkan.adreno.so "$PKG/libvulkan_freedreno.so"

COMMIT="$(git -C "$MESA_DIR" rev-parse --short HEAD)"
MESA_VER="$(cat "$MESA_DIR/VERSION")"
DATE="$(date -u +%Y%m%d)"
FPS_LABEL=$([ "$DEFAULT_FPS" = "0" ] && echo "" || echo "-${DEFAULT_FPS}fps")
NAME="PocketTurnip-A740-${MESA_VER}-${DATE}${FPS_LABEL}"

cat > "$PKG/meta.json" <<EOF
{
  "schemaVersion": 1,
  "name": "PocketTurnip A740 (Mesa $MESA_VER)",
  "description": "Turnip for Galaxy S23 / Adreno 740. Mesa $MESA_REF ($COMMIT), UBWC fix, frame limiter (default: ${DEFAULT_FPS} fps, 0 = off).",
  "author": "Hcode91",
  "packageVersion": "1",
  "vendor": "Mesa",
  "driverVersion": "Mesa $MESA_VER",
  "minApi": 31,
  "libraryName": "libvulkan_freedreno.so"
}
EOF

(cd "$PKG" && zip -q -9 "$OUT_DIR/$NAME.zip" libvulkan_freedreno.so meta.json)
echo "== Done: $OUT_DIR/$NAME.zip"
echo "name=$NAME" >> "${GITHUB_OUTPUT:-/dev/null}"

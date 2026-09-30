#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
version=${1:-0.1.0}
commit=$("$root/scripts/fetch_mesa.sh" "$root/work/mesa" "${MESA_REF:-main}")
"$root/scripts/build_android.sh" "$root/work/mesa"
"$root/scripts/build_linux.sh" "$root/work/mesa"
python3 "$root/scripts/package_bundle.py" --version "$version" --mesa-commit "$commit" \
  --mesa-version "$(tr -d '[:space:]' < "$root/work/mesa/VERSION")" --mesa-src "$root/work/mesa" \
  --out "$root/out" --dist "$root/dist"

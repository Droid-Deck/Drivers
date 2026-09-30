#!/usr/bin/env bash
set -euo pipefail
dest=$1
ref=${2:-main}
rm -rf "$dest"
git init -q "$dest"
git -C "$dest" fetch -q --depth=1 https://gitlab.freedesktop.org/mesa/mesa.git "$ref"
git -C "$dest" -c advice.detachedHead=false checkout -q FETCH_HEAD
git -C "$dest" rev-parse HEAD

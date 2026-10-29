#!/bin/sh
set -eu
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v uv >/dev/null 2>&1; then
    uv_path=$(command -v uv)
else
    uv_dir="$project_root/.local/tools/uv"
    uv_path="$uv_dir/uv"
    if [ ! -x "$uv_path" ]; then
        case "$(uname -s)" in
            Darwin) platform=apple-darwin ;;
            Linux) platform=unknown-linux-gnu ;;
            *) echo 'Utilisez run.cmd sous Windows.' >&2; exit 1 ;;
        esac
        case "$(uname -m)" in
            x86_64|amd64) arch=x86_64 ;;
            arm64|aarch64) arch=aarch64 ;;
            *) echo 'Architecture non prise en charge : x86_64 ou ARM64 requis.' >&2; exit 1 ;;
        esac
        if [ -f /etc/alpine-release ]; then
            echo 'Alpine/musl : utilisez une distribution Linux glibc (Ubuntu, Debian, Fedora) pour PyTorch.' >&2
            exit 1
        fi
        mkdir -p "$uv_dir"
        archive="uv-$arch-$platform.tar.gz"
        base_url=https://github.com/astral-sh/uv/releases/download/0.12.19
        download() {
            if command -v curl >/dev/null 2>&1; then
                curl --fail --location --retry 3 --output "$2" "$1"
            elif command -v wget >/dev/null 2>&1; then
                wget -O "$2" "$1"
            else
                echo 'curl ou wget est necessaire pour le premier telechargement.' >&2; exit 1
            fi
        }
        download "$base_url/$archive" "$uv_dir/$archive"
        download "$base_url/$archive.sha256" "$uv_dir/checksum.txt"
        expected=$(awk '{print $1}' "$uv_dir/checksum.txt")
        if command -v sha256sum >/dev/null 2>&1; then
            actual=$(sha256sum "$uv_dir/$archive" | awk '{print $1}')
        else
            actual=$(shasum -a 256 "$uv_dir/$archive" | awk '{print $1}')
        fi
        [ "$actual" = "$expected" ] || { echo 'Verification SHA256 de uv echouee.' >&2; exit 1; }
        tar -xzf "$uv_dir/$archive" -C "$uv_dir" --strip-components=1
    fi
fi
exec "$uv_path" run --no-project --python 3.12 "$project_root/run.py" "$@"

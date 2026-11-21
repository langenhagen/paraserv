#!/usr/bin/env bash
# Run Ollama with speech input via pollama.py and the project venv.
#
# Resolves symlinks, so it can be linked anywhere (e.g. into /usr/local/bin
# as `pollama`).
set -euo pipefail

script_path="$(readlink -f -- "${BASH_SOURCE[0]}")"
script_dir="$(dirname -- "$script_path")"

python_bin="${script_dir}/.venv/bin/python"
pollama_py="${script_dir}/pollama.py"

if [[ ! -x "$python_bin" ]]; then
    printf 'pollama: venv python not found at %s\nrun "uv sync" first\n' "$python_bin" >&2
    exit 1
fi

exec "$python_bin" "$pollama_py" "$@"

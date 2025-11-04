#!/usr/bin/env bash
set -e

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <project-path> [source-path]"
    echo "Example: $0 /home/yufu/aixcc_shared/CRSBench/benchmarks/atlanta-binutils-delta-01"
    echo "Example: $0 ~/benchmarks/my-project ~/src/my-source"
    exit 1
fi

PROJECT_PATH="$1"
SOURCE_PATH="${2:-}"

# Infer project name from basename
PROJECT_NAME=$(basename "$PROJECT_PATH")

echo "Building: $PROJECT_NAME"
echo "Project path: $PROJECT_PATH"
[[ -n "$SOURCE_PATH" ]] && echo "Source path: $SOURCE_PATH"

# Build command
if [[ -n "$SOURCE_PATH" ]]; then
    uv run oss-crs build example_configs/crs-libfuzzer "$PROJECT_NAME" "$SOURCE_PATH" --project-path "$PROJECT_PATH" --clone --overwrite
else
    uv run oss-crs build example_configs/crs-libfuzzer "$PROJECT_NAME" --project-path "$PROJECT_PATH" --clone --overwrite
fi

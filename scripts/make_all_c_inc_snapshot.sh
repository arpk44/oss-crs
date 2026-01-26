#!/bin/bash

# Make incremental build snapshots for all C projects and optionally push to registry
# Uses project.yaml inc_build and rts_mode settings for each project

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSS_CRS_DIR="$(dirname "$SCRIPT_DIR")"

# Default values
JOBS=1
PROJECT_LIST=""
BENCHMARKS_DIR=""
PUSH_MODE=""  # base, inc, both, or empty (no push)
RTS_TOOL=""   # If empty, uses project.yaml rts_mode
FORCE_REBUILD=false  # Default: skip rebuild if image exists
FORCE_PUSH=false     # Default: skip push if remote image exists
SKIP_CLONE=false
FORCE_PUSH=false

usage() {
    echo "Usage: $0 <OSS_FUZZ_PATH> -b <BENCHMARKS_DIR> [options]"
    echo ""
    echo "Arguments:"
    echo "  OSS_FUZZ_PATH       Path to OSS-Fuzz directory"
    echo ""
    echo "Required Options:"
    echo "  -b, --benchmarks-dir DIR  Benchmarks directory with bundled tarballs (pkgs/)"
    echo ""
    echo "Options:"
    echo "  -j, --jobs N        Number of parallel jobs (default: 1)"
    echo "  -l, --list FILE     File containing project names (one per line)"
    echo "  --push MODE         Push images to registry. MODE: base, inc, both"
    echo "  --rts-tool TOOL     RTS tool override: binaryrts (C/C++). If not specified, uses project.yaml rts_mode"
    echo "  --force-rebuild     Force rebuild even if local image exists (default: skip)"
    echo "  --force-push        Force push even if remote image exists (default: skip)"
    echo "  --skip-clone        Skip source code cloning"
    echo "  --force-push        Force push even if images already exist in remote registry"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 ../oss-fuzz -b ../../benchmarks --push both"
    echo "  $0 ../oss-fuzz -b ../../benchmarks -l projects.txt -j 4 --push inc"
    exit 1
}

# Parse arguments
if [ -z "$1" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    usage
fi

OSS_FUZZ_PATH="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--benchmarks-dir)
            BENCHMARKS_DIR="$2"
            shift 2
            ;;
        -j|--jobs)
            JOBS="$2"
            shift 2
            ;;
        -l|--list)
            PROJECT_LIST="$2"
            shift 2
            ;;
        --push)
            PUSH_MODE="$2"
            if [[ ! "$PUSH_MODE" =~ ^(base|inc|both)$ ]]; then
                echo "Error: --push requires MODE: base, inc, or both"
                exit 1
            fi
            shift 2
            ;;
        --rts-tool)
            RTS_TOOL="$2"
            shift 2
            ;;
        --force-rebuild)
            FORCE_REBUILD=true
            shift
            ;;
        --force-push)
            FORCE_PUSH=true
            shift
            ;;
        --skip-clone)
            SKIP_CLONE=true
            shift
            ;;
        --force-push)
            FORCE_PUSH=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

if [ -z "$BENCHMARKS_DIR" ]; then
    echo "Error: --benchmarks-dir is required"
    usage
fi

if [ ! -d "$BENCHMARKS_DIR" ]; then
    echo "Error: Benchmarks directory not found: $BENCHMARKS_DIR"
    exit 1
fi

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [ "$JOBS" -lt 1 ]; then
    echo "Error: jobs must be a positive integer"
    exit 1
fi

C_PROJECTS_DIR="$OSS_FUZZ_PATH/projects/aixcc/c"

LOG_DIR="$OSS_CRS_DIR/logs/c_inc_snapshot_$(date +%Y%m%d_%H%M%S)"
RESULT_DIR="$LOG_DIR/.results"
mkdir -p "$LOG_DIR" "$RESULT_DIR"

echo "=========================================="
echo "C Incremental Build Snapshot Maker"
echo "=========================================="
echo "OSS-Fuzz path:    $OSS_FUZZ_PATH"
echo "Benchmarks dir:   $BENCHMARKS_DIR"
echo "C projects:       $C_PROJECTS_DIR"
echo "Log directory:    $LOG_DIR"
echo "Parallel jobs:    $JOBS"
echo "Push mode:        ${PUSH_MODE:-none}"
echo "RTS tool:         ${RTS_TOOL:-from project.yaml}"
echo "Force rebuild:    $FORCE_REBUILD"
echo "Force push:       $FORCE_PUSH"
echo "Skip clone:       $SKIP_CLONE"

# Get list of projects
if [ -n "$PROJECT_LIST" ]; then
    if [ ! -f "$PROJECT_LIST" ]; then
        echo "Error: Project list file not found: $PROJECT_LIST"
        exit 1
    fi
    # Read projects from file (skip empty lines and comments)
    mapfile -t projects < <(grep -v '^#' "$PROJECT_LIST" | grep -v '^[[:space:]]*$')
    echo "Project list: $PROJECT_LIST"
else
    projects=($(ls -d "$C_PROJECTS_DIR"/*/ 2>/dev/null | xargs -n1 basename))
fi
echo "=========================================="

echo "Found ${#projects[@]} projects"
echo ""

total=${#projects[@]}

cd "$OSS_CRS_DIR"

# Build command options
build_cmd_opts() {
    local opts="--benchmarks-dir $BENCHMARKS_DIR"
    if [ -n "$RTS_TOOL" ]; then
        opts="$opts --rts-tool $RTS_TOOL"
    fi
    if [ -n "$PUSH_MODE" ]; then
        opts="$opts --push $PUSH_MODE"
    fi
    if [ "$FORCE_REBUILD" = false ]; then
        opts="$opts --no-rebuild"
    fi
    if [ "$FORCE_PUSH" = true ]; then
        opts="$opts --force-push"
    fi
    if [ "$SKIP_CLONE" = true ]; then
        opts="$opts --skip-clone"
    fi
    if [ "$FORCE_PUSH" = true ]; then
        opts="$opts --force-push"
    fi
    echo "$opts"
}

CMD_OPTS=$(build_cmd_opts)

# Function to run a single snapshot (used for parallel execution)
run_single_snapshot() {
    local project="$1"
    local log_dir="$2"
    local oss_fuzz_path="$3"
    local result_dir="$4"
    local cmd_opts="$5"

    local log_file="$log_dir/${project}.log"
    local result_file="$result_dir/${project}.result"

    if uv run oss-bugfix-crs make-inc-snapshot "aixcc/c/$project" "$oss_fuzz_path" $cmd_opts > "$log_file" 2>&1; then
        echo "PASSED" > "$result_file"
    else
        echo "FAILED" > "$result_file"
    fi
}
export -f run_single_snapshot

if [ "$JOBS" -eq 1 ]; then
    # Sequential execution with progress output
    current=0
    for project in "${projects[@]}"; do
        current=$((current + 1))
        echo "[$current/$total] Making snapshot: aixcc/c/$project"

        log_file="$LOG_DIR/${project}.log"
        result_file="$RESULT_DIR/${project}.result"

        if uv run oss-bugfix-crs make-inc-snapshot "aixcc/c/$project" "$OSS_FUZZ_PATH" $CMD_OPTS > "$log_file" 2>&1; then
            echo "  ✓ PASSED"
            echo "PASSED" > "$result_file"
        else
            echo "  ✗ FAILED (see $log_file)"
            echo "FAILED" > "$result_file"
        fi
    done
else
    # Parallel execution using xargs
    echo "Running snapshots in parallel..."
    printf '%s\n' "${projects[@]}" | xargs -P "$JOBS" -I {} bash -c \
        'run_single_snapshot "$@"' _ {} "$LOG_DIR" "$OSS_FUZZ_PATH" "$RESULT_DIR" "$CMD_OPTS"

    # Print results after parallel execution
    for project in "${projects[@]}"; do
        result_file="$RESULT_DIR/${project}.result"
        if [ -f "$result_file" ] && [ "$(cat "$result_file")" = "PASSED" ]; then
            echo "  ✓ aixcc/c/$project: PASSED"
        else
            echo "  ✗ aixcc/c/$project: FAILED (see $LOG_DIR/${project}.log)"
        fi
    done
fi

# Collect results
passed=0
failed=0
failed_projects=()

for project in "${projects[@]}"; do
    result_file="$RESULT_DIR/${project}.result"
    if [ -f "$result_file" ] && [ "$(cat "$result_file")" = "PASSED" ]; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        failed_projects+=("$project")
    fi
done

echo ""
echo "=========================================="
echo "Summary"
echo "=========================================="
echo "Total:  $total"
echo "Passed: $passed"
echo "Failed: $failed"

if [ ${#failed_projects[@]} -gt 0 ]; then
    echo ""
    echo "Failed projects:"
    for p in "${failed_projects[@]}"; do
        echo "  - $p"
    done
fi

# Write summary to file
cat > "$LOG_DIR/summary.txt" << EOF
C Incremental Build Snapshot Summary
=====================================
Date: $(date)
Parallel Jobs: $JOBS
Push mode: ${PUSH_MODE:-none}
RTS tool: ${RTS_TOOL:-from project.yaml}
Force rebuild: $FORCE_REBUILD
Force push: $FORCE_PUSH
Skip clone: $SKIP_CLONE
Force push: $FORCE_PUSH

Total: $total
Passed: $passed
Failed: $failed

Failed projects:
$(printf '%s\n' "${failed_projects[@]}")
EOF

echo ""
echo "Logs saved to: $LOG_DIR"

# Cleanup result files
rm -rf "$RESULT_DIR"

# Exit with error if any failed
[ $failed -eq 0 ]

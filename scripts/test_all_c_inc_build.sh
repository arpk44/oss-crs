#!/bin/bash

# Test all C projects with incremental build (no RTS)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSS_CRS_DIR="$(dirname "$SCRIPT_DIR")"

OSS_FUZZ_PATH="/mnt/ssd2/acorn421/team-atlanta/crsbench/oss-fuzz"
C_PROJECTS_DIR="$OSS_FUZZ_PATH/projects/aixcc/c"

LOG_DIR="$OSS_CRS_DIR/logs/c_inc_build_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "C Incremental Build Test Runner"
echo "=========================================="
echo "OSS-Fuzz path: $OSS_FUZZ_PATH"
echo "C projects:   $C_PROJECTS_DIR"
echo "Log directory: $LOG_DIR"
echo "=========================================="

# Get list of projects
projects=($(ls -d "$C_PROJECTS_DIR"/*/ 2>/dev/null | xargs -n1 basename))

echo "Found ${#projects[@]} projects"
echo ""

total=0
passed=0
failed=0
failed_projects=()

cd "$OSS_CRS_DIR"

for project in "${projects[@]}"; do
    total=$((total + 1))
    echo "[$total/${#projects[@]}] Testing: aixcc/c/$project"

    log_file="$LOG_DIR/${project}.log"

    if uv run oss-bugfix-crs test-inc-build "aixcc/c/$project" "$OSS_FUZZ_PATH" > "$log_file" 2>&1; then
        echo "  ✓ PASSED"
        passed=$((passed + 1))
    else
        echo "  ✗ FAILED (see $log_file)"
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
C Incremental Build Test Summary
================================
Date: $(date)
Total: $total
Passed: $passed
Failed: $failed

Failed projects:
$(printf '%s\n' "${failed_projects[@]}")
EOF

echo ""
echo "Logs saved to: $LOG_DIR"

# Exit with error if any failed
[ $failed -eq 0 ]

#!/bin/bash

# Test all JVM projects with RTS (Regression Test Selection)
# Runs both ekstazi and openclover for all projects

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSS_CRS_DIR="$(dirname "$SCRIPT_DIR")"

OSS_FUZZ_PATH="/mnt/ssd2/acorn421/team-atlanta/crsbench/oss-fuzz"
JVM_PROJECTS_DIR="$OSS_FUZZ_PATH/projects/aixcc/jvm"

# RTS tools to test
RTS_TOOLS=("jcgeks" "openclover")

# Get list of projects
projects=($(ls -d "$JVM_PROJECTS_DIR"/*/ 2>/dev/null | xargs -n1 basename))

cd "$OSS_CRS_DIR"

for rts_tool in "${RTS_TOOLS[@]}"; do
    echo ""
    echo "############################################"
    echo "# RTS Tool: $rts_tool"
    echo "############################################"
    echo ""

    LOG_DIR="$OSS_CRS_DIR/logs/jvm_rts_test_${rts_tool}_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$LOG_DIR"

    echo "OSS-Fuzz path: $OSS_FUZZ_PATH"
    echo "Log directory: $LOG_DIR"
    echo "Found ${#projects[@]} projects"
    echo ""

    total=0
    passed=0
    failed=0
    failed_projects=()

    for project in "${projects[@]}"; do
        total=$((total + 1))
        echo "[$total/${#projects[@]}] Testing: aixcc/jvm/$project"

        log_file="$LOG_DIR/${project}.log"

        if uv run oss-bugfix-crs test-inc-build "aixcc/jvm/$project" "$OSS_FUZZ_PATH" --with-rts --rts-tool "$rts_tool" > "$log_file" 2>&1; then
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
    echo "Summary for $rts_tool"
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
JVM RTS Test Summary
====================
Date: $(date)
RTS Tool: $rts_tool
Total: $total
Passed: $passed
Failed: $failed

Failed projects:
$(printf '%s\n' "${failed_projects[@]}")
EOF

    echo ""
    echo "Logs saved to: $LOG_DIR"
done

echo ""
echo "############################################"
echo "# All RTS tools tested!"
echo "############################################"

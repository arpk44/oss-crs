# justfile for oss-crs

# Run type checking with pyright
typecheck:
    uv run --all-extras ty check

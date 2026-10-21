#!/bin/sh
# The execution environment exposes .git as an empty read-only directory.
# Use explicit metadata without modifying protected app mounts.
set -eu
cd "$(dirname "$0")/.."
exec git --git-dir=.git-local --work-tree=. "$@"

# Archive Folder

This directory stores non-essential runtime artifacts moved out of active project paths.

## What goes here
- Test/runtime caches (for example: `.pytest_cache`, `__pycache__`)
- Historical logs (for example: evaluation logs)
- Temporary/generated artifacts that are not required for normal CLI/UI workflows

## What should stay outside archive
- `output/*.json` recommendation files used by validation/demo flows
- Source code, tests, and active documentation

## Current structure
- `cache/` → archived cache directories
- `logs/` → archived logs

Use this folder to keep the project root clean without breaking operational commands.

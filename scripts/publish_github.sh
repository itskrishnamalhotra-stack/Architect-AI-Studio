#!/usr/bin/env bash
# Publishes this project to the owner's EXISTING public GitHub repository.
set -euo pipefail
repo='itskrishnamalhotra-stack/Architect-AI-Studio'
url="https://github.com/$repo.git"
command -v git >/dev/null || { echo 'Install Git first.' >&2; exit 1; }
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -d .git ] || git init -b main
if git remote get-url origin >/dev/null 2>&1; then
  existing=$(git remote get-url origin)
  [ "$existing" = "$url" ] || { echo "Unexpected origin: $existing" >&2; exit 1; }
else
  git remote add origin "$url"
fi
git add -A
if ! git diff --cached --quiet; then
  git commit -m 'Initial release: Architect AI Studio V4.1 with examples and docs'
fi
git branch -M main
git push -u origin main
echo "Published: https://github.com/$repo"

#!/bin/bash
set -e
if [ -z "$1" ]; then
  echo "Error: Commit message is required."
  exit 1
fi
mv ai-reference ai-reference-hide
git add .
git commit -m "$1"
mv ai-reference-hide ai-reference
git push

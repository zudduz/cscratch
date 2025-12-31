#!/bin/bash
set -e

# Function to be called on exit
cleanup() {
  if [ -d "ai-reference-hide" ]; then
    mv ai-reference-hide ai-reference
  fi
}

# Register the cleanup function to be called on EXIT
trap cleanup EXIT

if [ -z "$1" ]; then
  echo "Error: Commit message is required."
  exit 1
fi

# Only move the directory if it exists
if [ -d "ai-reference" ]; then
  mv ai-reference ai-reference-hide
fi

git add .
git commit -m "$1"
git push

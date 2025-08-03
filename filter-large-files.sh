#!/bin/bash

echo "Removing large files from git history..."

# Set warning suppression
export FILTER_BRANCH_SQUELCH_WARNING=1

# Create the index filter command to remove large files
INDEX_FILTER="git rm --cached --ignore-unmatch \
  'data/models/*.tflite' \
  'model/*.tflite' \
  'models/*.tflite' \
  '*.tflite' \
  '*.whl' \
  'data/database/*.db' \
  'data/*.db' \
  '*.db' \
  'ioc_reference.db' \
  'tflite_runtime*.whl' \
  'data/ioc_data_v*.json' \
  'ioc_data_v*.json'"

# Run filter-branch to remove the files from all commits
git filter-branch --force --index-filter "$INDEX_FILTER" --prune-empty --tag-name-filter cat -- --all

echo "Cleaning up git refs and garbage collection..."
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "Large files removed from git history!"
echo "Repository size before and after:"
du -sh .

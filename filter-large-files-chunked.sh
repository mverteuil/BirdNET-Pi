#!/bin/bash

echo "Removing large files from git history in chunks..."

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

echo "Processing main branch..."
git filter-branch --force --index-filter "$INDEX_FILTER" --prune-empty --tag-name-filter cat main

echo "Processing feature/php2python branch..."
git filter-branch --force --index-filter "$INDEX_FILTER" --prune-empty --tag-name-filter cat feature/php2python

echo "Processing other branches..."
git filter-branch --force --index-filter "$INDEX_FILTER" --prune-empty --tag-name-filter cat -- --branches

echo "Processing tags..."
git filter-branch --force --index-filter "$INDEX_FILTER" --prune-empty --tag-name-filter cat -- --tags

echo "Cleaning up git refs and garbage collection..."
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "Large files removed from git history!"
echo "Repository size:"
du -sh .

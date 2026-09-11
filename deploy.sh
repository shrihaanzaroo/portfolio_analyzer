#!/bin/bash
set -e

echo "Checking for syntax errors..."
python3 -m py_compile *.py

echo "Syntax OK. Pushing to GitHub..."
git add *.py requirements.txt
git commit -m "${1:-Update app}"
git push

echo "Done — Streamlit Cloud should redeploy in a minute or two."

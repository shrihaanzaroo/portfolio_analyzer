#!/bin/bash
set -e

echo "Checking for syntax errors..."
python3 -m py_compile portfolio_analyzer.py engine.py reference_data.py

echo "Syntax OK. Pushing to GitHub..."
git add portfolio_analyzer.py engine.py reference_data.py requirements.txt
git commit -m "${1:-Update app}"
git push

echo "Done — Streamlit Cloud should redeploy in a minute or two."

#!/bin/bash
set -e

echo "Checking for syntax errors..."
python3 -m py_compile *.py

echo "Syntax OK. Running tests..."
if [ -d .venv ]; then
    .venv/bin/python -m pytest -q
else
    python3 -m pytest -q
fi

echo "Tests passed. Pushing to GitHub..."
git add *.py requirements.txt requirements-dev.txt pytest.ini tests/
git commit -m "${1:-Update app}"
git push

echo "Done — Streamlit Cloud should redeploy in a minute or two."

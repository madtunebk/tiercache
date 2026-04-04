#!/bin/bash
# Usage: ./release.sh 0.1.4

set -e

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh <version>"
    echo "Example: ./release.sh 0.1.4"
    exit 1
fi

echo "Releasing v$VERSION..."

# Bump version
sed -i "s/^version = .*/version = \"$VERSION\"/" pyproject.toml

# Build
rm -rf dist/
.venv/bin/python -m build

# Upload to PyPI
.venv/bin/twine upload dist/*

# Commit and push to GitHub
git add pyproject.toml CHANGELOG.md
git commit -m "Release v$VERSION"
git tag "v$VERSION"
git push
git push --tags

echo "Done! v$VERSION is live on PyPI and GitHub."

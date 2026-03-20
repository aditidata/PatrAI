#!/bin/bash
# Build frontend and copy dist into backend static folder
set -e

echo "Building React frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Copying dist to static/..."
rm -rf static
cp -r frontend/dist static

echo "Build complete. Run: uvicorn main:app --reload"

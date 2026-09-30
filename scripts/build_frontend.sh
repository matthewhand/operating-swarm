#!/bin/bash
set -e

echo "Building Operating Swarm MCP frontend..."

# Check if we're in the right directory
if [ ! -d "webui/frontend" ]; then
    echo "Error: webui/frontend directory not found"
    echo "Please run this script from the project root directory"
    exit 1
fi

# Check if npm is available
if ! command -v npm &> /dev/null; then
    echo "Error: npm not found. Please install Node.js (v22+ recommended)"
    exit 1
fi

# Navigate to frontend directory
cd webui/frontend

echo "Installing dependencies..."
if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund --legacy-peer-deps
else
    npm install --no-audit --no-fund --legacy-peer-deps
fi

echo "Building frontend assets..."
npm run build

if [ ! -f dist/index.html ]; then
    echo "Error: dist/index.html missing after build"
    exit 1
fi

echo "Frontend build complete!"
echo "Assets are in: $(pwd)/dist"

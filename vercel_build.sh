#!/bin/bash
# Build script for Vercel deployment

# Create a static directory in the root if it doesn't exist
mkdir -p static

# Copy static files from src/diet_planner/static to root static directory
cp -r src/diet_planner/static/* static/ 2>/dev/null || echo "No static files to copy, continuing..."

echo "Build script completed successfully"
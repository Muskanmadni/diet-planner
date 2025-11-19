#!/bin/bash
# Custom build script for Vercel to handle dependencies correctly

# Set environment variable to force SQLite usage
export FORCE_SQLITE=true

# Install dependencies without psycopg2 to avoid compilation issues
# Use our custom requirements file that doesn't include psycopg2
pip install --no-cache-dir --target="$HOME/site-packages" -r requirements-vercel.txt --no-binary psycopg2

# Install SQLite-specific dependencies if needed
pip install --no-cache-dir --target="$HOME/site-packages" pysqlite3-binary

echo "Build completed successfully"
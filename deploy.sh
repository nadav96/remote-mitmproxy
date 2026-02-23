#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
S3_BUCKET="your-s3-bucket"
S3_PREFIX="remote-mitmproxy/scripts"

# Upload addon script to S3
echo "Uploading addon script to S3..."
aws s3 cp "$SCRIPT_DIR/app/scripts/addon.py" "s3://$S3_BUCKET/$S3_PREFIX/addon.py"

# Build template and deploy
echo "Building template..."
rocketsam template

echo "Deploying..."
rocketsam deploy

#!/usr/bin/env bash
# Publish the ZIP to a GitHub Release using curl. Requires GITHUB_TOKEN env var.
REPO=${1:-sudeepdas12/IPO-Bulk-Apply}
TAG=${2:-v0.0.9}
ZIP=${3:-dist/meroshare-bot-0.0.9.zip}

if [ ! -f "$ZIP" ]; then
  echo "Asset not found: $ZIP" >&2
  exit 1
fi
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Set GITHUB_TOKEN environment variable with a PAT that has 'repo' scope." >&2
  exit 1
fi

CREATE_URL="https://api.github.com/repos/$REPO/releases"
RESPONSE=$(curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" -H "Content-Type: application/json" -d "{\"tag_name\": \"$TAG\", \"name\": \"$TAG\", \"body\": \"Release built from local workspace\"}" "$CREATE_URL")
UPLOAD_URL=$(echo "$RESPONSE" | jq -r .upload_url | sed -e 's/{.*$//')

if [ -z "$UPLOAD_URL" ] || [ "$UPLOAD_URL" = "null" ]; then
  echo "Failed to create release:" >&2
  echo "$RESPONSE" | jq -r .message
  exit 1
fi

curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" -H "Content-Type: application/zip" --data-binary @"$ZIP" "$UPLOAD_URL?name=$(basename $ZIP)"

echo "Uploaded $ZIP to release $TAG in $REPO"
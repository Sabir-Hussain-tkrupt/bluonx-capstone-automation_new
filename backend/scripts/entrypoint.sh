#!/bin/sh
set -e

# Create secrets directory in container if it doesn't exist
mkdir -p /app/secrets

# If DOCUSIGN_PRIVATE_KEY_SECRET environment variable is set from Secrets Manager,
# write its content to /app/secrets/docusign_private_key.pem
if [ -n "$DOCUSIGN_PRIVATE_KEY_SECRET" ]; then
    echo "$DOCUSIGN_PRIVATE_KEY_SECRET" > /app/secrets/docusign_private_key.pem
    chmod 600 /app/secrets/docusign_private_key.pem
fi

# Execute the CMD passed to docker (or default uvicorn command)
exec "$@"

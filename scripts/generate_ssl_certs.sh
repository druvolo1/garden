#!/bin/bash
# Script to generate self-signed SSL certificates for HTTPS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CERT_DIR="$PROJECT_ROOT/certs"

echo "Generating self-signed SSL certificates..."
echo "Certificate directory: $CERT_DIR"

# Create certs directory if it doesn't exist
mkdir -p "$CERT_DIR"

# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -nodes \
    -out "$CERT_DIR/cert.pem" \
    -keyout "$CERT_DIR/key.pem" \
    -days 365 \
    -subj "/C=US/ST=State/L=City/O=Organization/OU=Department/CN=localhost"

if [ $? -eq 0 ]; then
    echo "✓ SSL certificates generated successfully!"
    echo "  Certificate: $CERT_DIR/cert.pem"
    echo "  Private Key: $CERT_DIR/key.pem"
    echo ""
    echo "To enable HTTPS:"
    echo "1. Add '\"use_https\": true' to your data/settings.json file"
    echo "2. Restart the application"
    echo ""
    echo "Note: This is a self-signed certificate. Your browser will show a security warning."
    echo "You'll need to accept the security exception to access the site."
else
    echo "✗ Failed to generate SSL certificates"
    exit 1
fi

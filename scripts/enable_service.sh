#!/bin/bash
# File: scripts/enable_service.sh
# Purpose: Enable and start the garden.service for normal operation

set -e

echo "=============================================="
echo "  Enabling and Starting garden.service"
echo "=============================================="
echo ""

# Enable service to start on boot
echo "[1/2] Enabling garden.service to start on boot..."
sudo systemctl enable garden.service
echo "✓ Service enabled"
echo ""

# Start service now
echo "[2/2] Starting garden.service..."
sudo systemctl start garden.service
echo "✓ Service started"
echo ""

# Show status
echo "Service status:"
sudo systemctl status garden.service --no-pager -l
echo ""
echo "=============================================="
echo "  garden.service is now enabled and running"
echo "=============================================="
echo ""
echo "Useful commands:"
echo "  - Check logs: journalctl -u garden.service -f"
echo "  - Check status: systemctl status garden.service"
echo "  - Restart: sudo systemctl restart garden.service"

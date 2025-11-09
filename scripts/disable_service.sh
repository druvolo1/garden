#!/bin/bash
# File: scripts/disable_service.sh
# Purpose: Stop and disable the garden.service for manual troubleshooting

set -e

echo "=============================================="
echo "  Stopping and Disabling garden.service"
echo "=============================================="
echo ""

# Stop service
echo "[1/2] Stopping garden.service..."
sudo systemctl stop garden.service
echo "✓ Service stopped"
echo ""

# Disable service from starting on boot
echo "[2/2] Disabling garden.service from starting on boot..."
sudo systemctl disable garden.service
echo "✓ Service disabled"
echo ""

# Show status
echo "Service status:"
sudo systemctl status garden.service --no-pager -l || true
echo ""
echo "=============================================="
echo "  garden.service is now stopped and disabled"
echo "=============================================="
echo ""
echo "You can now run the application manually for troubleshooting:"
echo "  cd $(dirname $(dirname $(readlink -f $0)))"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "To re-enable the service later, run:"
echo "  ./scripts/enable_service.sh"

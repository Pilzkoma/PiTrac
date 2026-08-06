#!/bin/bash
# Jetson LM — Install systemd services for auto-start
# Run as: sudo bash setup_services.sh
#
# This installs two services:
#   jetson-lm-receiver  — shot receiver (Unix socket + TCP forwarding + DB logging)
#   jetson-lm-dashboard — Flask stats dashboard on port 5000
#
# After install:
#   sudo systemctl start jetson-lm-receiver
#   sudo systemctl start jetson-lm-dashboard
#   sudo systemctl status jetson-lm-receiver
#   sudo systemctl status jetson-lm-dashboard
#
# View logs:
#   journalctl -u jetson-lm-receiver -f
#   journalctl -u jetson-lm-dashboard -f
#
# To change receiver settings (IP, player, port), edit:
#   /etc/systemd/system/jetson-lm-receiver.service
#   Then: sudo systemctl daemon-reload && sudo systemctl restart jetson-lm-receiver

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Jetson LM Service Installer ==="
echo ""

# Check we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo bash setup_services.sh)"
    exit 1
fi

# Check files exist
for f in shot_receiver.py dashboard.py shot_db.py ball_physics.py; do
    if [ ! -f "$SCRIPT_DIR/$f" ]; then
        echo "ERROR: $f not found in $SCRIPT_DIR"
        exit 1
    fi
done

# Copy service files
echo "[1/4] Installing service files..."
cp "$SCRIPT_DIR/jetson-lm-receiver.service" /etc/systemd/system/
cp "$SCRIPT_DIR/jetson-lm-dashboard.service" /etc/systemd/system/

# Reload systemd
echo "[2/4] Reloading systemd..."
systemctl daemon-reload

# Enable services (start on boot)
echo "[3/4] Enabling services for auto-start on boot..."
systemctl enable jetson-lm-receiver
systemctl enable jetson-lm-dashboard

echo "[4/4] Done!"
echo ""
echo "=== Services installed and enabled ==="
echo ""
echo "To start now:"
echo "  sudo systemctl start jetson-lm-dashboard"
echo "  sudo systemctl start jetson-lm-receiver"
echo ""
echo "To check status:"
echo "  sudo systemctl status jetson-lm-dashboard"
echo "  sudo systemctl status jetson-lm-receiver"
echo ""
echo "To view live logs:"
echo "  journalctl -u jetson-lm-receiver -f"
echo "  journalctl -u jetson-lm-dashboard -f"
echo ""
echo "To change receiver IP/player/port:"
echo "  sudo nano /etc/systemd/system/jetson-lm-receiver.service"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl restart jetson-lm-receiver"
echo ""
echo "Dashboard will be available at:"
echo "  http://$(hostname -I | awk '{print $1}'):5000"
echo ""

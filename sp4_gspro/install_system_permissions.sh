#!/bin/bash
# Jetson LM — allow the dashboard to power the Jetson off and to restart its
# own services, without a password.
# Run once as: sudo bash sp4_gspro/install_system_permissions.sh
#
# Grants the user `brain` exactly these commands as root, nothing else:
#   systemctl poweroff                       the "Herunterfahren" button and Golfinator
#   systemctl restart jetson-lm-dashboard    redeploying the dashboard over SSH
#   systemctl restart jetson-lm-receiver     redeploying the receiver over SSH
#
# Undo: sudo rm /etc/sudoers.d/jetson-lm

set -e

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root (sudo bash $0)"
    exit 1
fi

TARGET=/etc/sudoers.d/jetson-lm
TMP=$(mktemp)

cat > "$TMP" <<'EOF'
# Written by JetsonLM sp4_gspro/install_system_permissions.sh
brain ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
brain ALL=(root) NOPASSWD: /usr/bin/systemctl restart jetson-lm-dashboard
brain ALL=(root) NOPASSWD: /usr/bin/systemctl restart jetson-lm-receiver
EOF

# A broken sudoers file can lock sudo out entirely, so check before installing.
if ! visudo -cf "$TMP"; then
    echo "ERROR: generated sudoers file did not validate, nothing installed"
    rm -f "$TMP"
    exit 1
fi

install -m 0440 -o root -g root "$TMP" "$TARGET"
rm -f "$TMP"

echo "Installed $TARGET:"
cat "$TARGET"
echo
echo "Check as brain:  sudo -n -l /usr/bin/systemctl poweroff"

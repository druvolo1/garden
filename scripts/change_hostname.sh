#!/bin/bash
# change_hostname.sh
# Usage: sudo ./change_hostname.sh new-hostname

# Immediately exit if any command fails
set -e

# Where this script sits:
SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Log file in the same folder as the script:
LOGFILE="${SCRIPTDIR}/change_hostname.log"

# Redirect script output to console + logfile
exec > >(tee -a "$LOGFILE") 2>&1

if [[ $# -lt 1 ]]; then
  echo "[ERROR] No new hostname specified!"
  echo "Usage: $0 NEW_HOSTNAME"
  exit 1
fi

NEW_HOSTNAME="$1"
OLD_HOSTNAME="$(hostname)"

echo "[$(date)] Changing hostname from '$OLD_HOSTNAME' to '$NEW_HOSTNAME'..."

# 1) Update /etc/hosts
#    - Remove old hostname if it exists on a 127.x.x.x line.
#    - Then ensure there's a line for new hostname on 127.0.1.1 (common on Debian/Ubuntu).
#      If your distro uses 127.0.0.1 instead, just swap that in below.

HOSTS_FILE="/etc/hosts"

echo "Updating /etc/hosts..."

# A simple approach: remove lines that contain the old hostname (if you wish to remove them),
# but only if they start with 127. or if they'd break other lines (like IPv6).
# Then we ensure new hostname is appended to the 127.0.1.1 line.

sudo sed -i "/127\..*$OLD_HOSTNAME/d" "$HOSTS_FILE"

# If there's already a line for 127.0.1.1, we just add the new hostname to the end of that line
# if it's not already present. Otherwise, create a new line.
# This quick inline approach checks if '127.0.1.1' exists, and if so, adds $NEW_HOSTNAME; 
# if not, it appends a brand new line at the end.
grep -q "^127.0.1.1" "$HOSTS_FILE" && \
  sudo sed -i "s/^127.0.1.1.*/& $NEW_HOSTNAME/" "$HOSTS_FILE" || \
  sudo bash -c "echo '127.0.1.1   $NEW_HOSTNAME' >> '$HOSTS_FILE'"

# 2) Actually set the new hostname via hostnamectl
echo "Setting hostname with hostnamectl..."
sudo hostnamectl set-hostname "$NEW_HOSTNAME"

echo "[$(date)] Hostname change script finished successfully."

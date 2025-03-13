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

HOSTS_FILE="/etc/hosts"

echo "Updating /etc/hosts..."

# 1) Remove the old hostname from 127.x.x.x lines (word-boundary match).
#    This ensures you won't keep old references.
sudo sed -i "s/\b$OLD_HOSTNAME\b//g" "$HOSTS_FILE"

# 2) Now overwrite the '127.0.1.1' line with the new hostname only.
#    If there's no line matching '^127.0.1.1', append a new one.
if grep -q "^127.0.1.1" "$HOSTS_FILE"; then
    sudo sed -i "s/^127.0.1.1.*/127.0.1.1   $NEW_HOSTNAME/" "$HOSTS_FILE"
else
    echo "127.0.1.1   $NEW_HOSTNAME" | sudo tee -a "$HOSTS_FILE" >/dev/null
fi

# 3) Actually set the new hostname via hostnamectl
echo "Setting hostname with hostnamectl..."
sudo hostnamectl set-hostname "$NEW_HOSTNAME"

echo "[$(date)] Hostname change script finished successfully."

#4) Restart Avahi so the new mDNS name registers from the new hostname
#Ssudo systemctl restart avahi-daemon

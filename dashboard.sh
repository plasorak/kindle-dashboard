#!/bin/sh

CURL=/mnt/us/usbnet/bin/curl
FBINK=/mnt/us/usbnet/bin/fbink
IMG=/tmp/dashboard.png

# --- Display prep ---
echo 0 > /sys/class/graphics/fb0/rotate 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

# Fetch dashboard image
${CURL} -s --max-time 30 -o "${IMG}" "http://192.168.1.86:5000/dashboard.png"

if [ ! -f "${IMG}" ] || [ ! -s "${IMG}" ]; then
    ${FBINK} -c -q
    ${FBINK} -q "Failed to fetch dashboard from 192.168.1.86:5000"
    exit 1
fi

# Check battery percentage via LIPC (Kindle's IPC system)
BATTERY=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null)
[ -z "${BATTERY}" ] && BATTERY=100

# Clear screen
${FBINK} -f -s
${FBINK} -c -q

# Display image; invert colors if battery < 10% as a low-battery warning
if [ "${BATTERY}" -lt 10 ]; then
    ${FBINK} -g file="${IMG}" -h
else
    ${FBINK} -g file="${IMG}"
fi

# Overlay battery level at top right
${FBINK} -q -x -5 -y -1 "${BATTERY}%"

exit 0

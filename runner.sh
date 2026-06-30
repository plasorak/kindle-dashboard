#!/bin/sh
# Keep the dashboard alive and updating

#!/bin/sh
stop framework 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

while true ; do
    echo "running update at $(date)..."
    /mnt/us/weather/dashboard.sh
    sleep 600 # 10 min
    echo "... done"
done

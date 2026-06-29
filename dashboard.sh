#!/bin/sh
#
# Kindle e-ink dashboard: Oxford 7-day weather + Octopus Agile electricity
# Paints the whole screen in one pass (landscape).
#

# --- Paths ---
CURL=/mnt/us/usbnet/bin/curl
JQ=/mnt/us/usbnet/bin/jq
FBINK=/mnt/us/usbnet/bin/fbink
TZF='/mnt/us/weather/zoneinfo/London'

# --- Location: Oxford ---
LAT=51.7520
LON=-1.2577

# --- Octopus Agile ---
PRODUCT="AGILE-24-10-01"
REGION="H"
TARIFF="E-1R-${PRODUCT}-${REGION}"

# --- Display prep ---
echo 0 > /sys/class/graphics/fb0/rotate 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

# Helper: UTC ISO8601 -> local HH:MM (honours BST/GMT via zoneinfo file)
iso_to_local() {
    # $1 = ISO string like 2026-06-29T22:30:00Z, $2 = date format
    _epoch=$(date -u -d "$(echo "$1" | sed 's/T/ /; s/Z//')" '+%s' 2>/dev/null)
    [ -z "${_epoch}" ] && { echo "$1" ; return ; }
    TZ="${TZF}" date -d "@${_epoch}" "$2" 2>/dev/null
}

# --- Map a WMO weathercode to a short label ---
wmo_desc() {
    case "$1" in
        0)            echo "Clear" ;;
        1)            echo "Mainly clear" ;;
        2)            echo "Part cloudy" ;;
        3)            echo "Overcast" ;;
        45|48)        echo "Fog" ;;
        51|53|55)     echo "Drizzle" ;;
        56|57)        echo "Frz drizzle" ;;
        61|63|65)     echo "Rain" ;;
        66|67)        echo "Frz rain" ;;
        71|73|75)     echo "Snow" ;;
        77)           echo "Snow grains" ;;
        80|81|82)     echo "Showers" ;;
        85|86)        echo "Snow showers" ;;
        95)           echo "Thunderstorm" ;;
        96|99)        echo "Thunder/hail" ;;
        *)            echo "?" ;;
    esac
}

# =====================================================================
# FETCH
# =====================================================================

WURL="https://api.open-meteo.com/v1/forecast?latitude=${LAT}&longitude=${LON}&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=Europe%2FLondon&forecast_days=7"
WJSON=$(${CURL} -s --max-time 30 "${WURL}")

NOW=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
EURL="https://api.octopus.energy/v1/products/${PRODUCT}/electricity-tariffs/${TARIFF}/standard-unit-rates/?period_from=${NOW}"
EJSON=$(${CURL} -s --max-time 30 "${EURL}")

# =====================================================================
# DRAW
# =====================================================================

# Clear once, draw everything with -b (no per-line refresh), then one refresh at end.
${FBINK} -f -s
${FBINK} -c -q

# ---------------- Weather (top) ----------------
${FBINK} -q -b -y 1 "  Oxford weather"
${FBINK} -q -b -y 3 "  Day  Date    Conditions     Hi/Lo    Rain"

if [ -z "${WJSON}" ] ; then
    ${FBINK} -q -b -y 5 "  Weather fetch failed"
else
    ROWS=$(echo "${WJSON}" | ${JQ} -r '
        .daily as $d
        | range(0; ($d.time | length))
        | "\($d.time[.])\t\($d.weathercode[.])\t\($d.temperature_2m_max[.])\t\($d.temperature_2m_min[.])\t\($d.precipitation_probability_max[.])"
    ')
    LINE=5
    echo "${ROWS}" | while IFS="$(printf '\t')" read DATE CODE TMAX TMIN PRECIP ; do
        DOW=$(TZ="${TZF}" date -d "${DATE}" '+%a' 2>/dev/null)
        [ -z "${DOW}" ] && DOW="--"
        SHORT=$(echo "${DATE}" | awk -F- '{print $3"/"$2}')
        DESC=$(wmo_desc "${CODE}")
        HI=$(echo "${TMAX}" | cut -d. -f1)
        LO=$(echo "${TMIN}" | cut -d. -f1)
        TEXT=$(printf "  %-3s  %-6s  %-13s  %2s/%-2s C  %3s%%" "${DOW}" "${SHORT}" "${DESC}" "${HI}" "${LO}" "${PRECIP}")
        ${FBINK} -q -b -y ${LINE} "${TEXT}"
        LINE=$((LINE + 1))
    done
fi

# ---------------- Divider ----------------
# ${FBINK} -q -b -y 13 "  ==============================================="
${FBINK} -q -b -y 13 "  _______________________________________________"

# ---------------- Electricity (bottom) ----------------
${FBINK} -q -b -y 14 "  Octopus Agile"

if [ -z "${EJSON}" ] ; then
    ${FBINK} -q -b -y 16 "  Electricity fetch failed"
else
    SLOTS=$(echo "${EJSON}" | ${JQ} -r '.results | sort_by(.valid_from)[] | "\(.valid_from)\t\(.value_inc_vat)"')

    if [ -z "${SLOTS}" ] ; then
        ${FBINK} -q -b -y 16 "  No price data yet"
    else
        # --- Cheapest contiguous 4h (8-slot) window for the washing machine ---
        WINDOW=$(echo "${EJSON}" | ${JQ} -r '
          [.results | sort_by(.valid_from)[] | {t: .valid_from, p: .value_inc_vat}] as $s
          | [ range(0; ($s|length) - 7)
              | { start: $s[.].t,
                  avg: ( [ $s[ . : .+8 ][].p ] | add / 8 ) } ]
          | min_by(.avg)
          | "\(.start)\t\(.avg)"
        ')
        WIN_VF=$(echo "${WINDOW}" | cut -f1)
        WIN_AVG=$(echo "${WINDOW}" | cut -f2)
        WIN_EPOCH=$(date -u -d "$(echo "${WIN_VF}" | sed 's/T/ /; s/Z//')" '+%s' 2>/dev/null)
        WIN_START=$(TZ="${TZF}" date -d "@${WIN_EPOCH}" '+%a %H:%M' 2>/dev/null)
        WIN_END=$(TZ="${TZF}" date -d "@$((WIN_EPOCH + 14400))" '+%H:%M' 2>/dev/null)
        WIN_AVG_R=$(echo "${WIN_AVG}" | awk '{printf "%.1f", $0}')

        # Headline: when to run the washing machine
        ${FBINK} -q -b -y 16 "  Cheapest 4 hours: ${WIN_START} - ${WIN_END}"
        ${FBINK} -q -b -y 17 "  (avg ${WIN_AVG_R}p/kWh)"



        # --- Most expensive contiguous 2h (4-slot) ---
        WINDOW=$(echo "${EJSON}" | ${JQ} -r '
          [.results | sort_by(.valid_from)[] | {t: .valid_from, p: .value_inc_vat}] as $s
          | [ range(0; ($s|length) - 7)
              | { start: $s[.].t,
                  avg: ( [ $s[ . : .+4 ][].p ] | add / 4 ) } ]
          | max_by(.avg)
          | "\(.start)\t\(.avg)"
        ')
        WIN_VF=$(echo "${WINDOW}" | cut -f1)
        WIN_AVG=$(echo "${WINDOW}" | cut -f2)
        WIN_EPOCH=$(date -u -d "$(echo "${WIN_VF}" | sed 's/T/ /; s/Z//')" '+%s' 2>/dev/null)
        WIN_START=$(TZ="${TZF}" date -d "@${WIN_EPOCH}" '+%a %H:%M' 2>/dev/null)
        WIN_END=$(TZ="${TZF}" date -d "@$((WIN_EPOCH + 14400))" '+%H:%M' 2>/dev/null)
        WIN_AVG_R=$(echo "${WIN_AVG}" | awk '{printf "%.1f", $0}')

        # Headline: when to run the washing machine
        ${FBINK} -q -b -y 19 "  Most expensive 2 hours: ${WIN_START} - ${WIN_END}"
        ${FBINK} -q -b -y 20 "  (avg ${WIN_AVG_R}p/kWh)"
	
    fi
fi

# ---------------- Footer ----------------
${FBINK} -q -b -y 36 "  Updated: $(TZ="${TZF}" date '+%a %d %b %H:%M %Z')"

# One clean refresh to push everything to the panel at once
${FBINK} -s >/dev/null 2>&1

exit 0

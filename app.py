#!/usr/bin/env python3
import io
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import requests
from flask import Flask, Response, redirect, render_template_string
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

WIDTH = 800
HEIGHT = 600
TZ_NAME = "Europe/London"
FONT_DIR = "/usr/java/lib/fonts"
ICON_DIR = os.path.join(os.path.dirname(__file__), "weather_icons")
WEATHER_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=51.7520&longitude=-1.2577"
    "&daily=weathercode,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&hourly=precipitation_probability"
    "&timezone=Europe%2FLondon&forecast_days=7"
)
OCTOPUS_PRODUCT = "AGILE-24-10-01"
OCTOPUS_REGION = "H"
OCTOPUS_TARIFF = f"E-1R-{OCTOPUS_PRODUCT}-{OCTOPUS_REGION}"
OCTOPUS_URL_TEMPLATE = (
    "https://api.octopus.energy/v1/products/{product}/electricity-tariffs/{tariff}/standard-unit-rates/"
    "?period_from={period_from}"
)

WEATHER_ROWS = 7
WEATHER_ROW_HEIGHT = 33
TOP_MARGIN = 52
COLUMN_X = [18, 104, 208, 360, 532, 640]

SYSTEM_FONT_FALLBACKS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def find_font(name_fragment=""):
    if os.path.isdir(FONT_DIR):
        for root, _, files in os.walk(FONT_DIR):
            for f in files:
                if not f.lower().endswith((".ttf", ".otf")):
                    continue
                if name_fragment and name_fragment.lower() not in f.lower():
                    continue
                return os.path.join(root, f)

        for root, _, files in os.walk(FONT_DIR):
            for f in files:
                if not f.lower().endswith((".ttf", ".otf")):
                    continue
                f_lower = f.lower()
                if "liberationsans" in f_lower or "dejavusans" in f_lower:
                    return os.path.join(root, f)

        for root, _, files in os.walk(FONT_DIR):
            for f in files:
                if f.lower().endswith((".ttf", ".otf")):
                    return os.path.join(root, f)

    return None


def find_font_path():
    path = find_font("arial") or find_font("sans") or find_font()
    if path:
        return path
    for p in SYSTEM_FONT_FALLBACKS:
        if os.path.exists(p):
            return p
    try:
        from matplotlib import font_manager as fm
        p = fm.findfont("DejaVu Sans")
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    return None


def load_font(size=18):
    path = find_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def iso_to_local(iso_string, fmt="%a %H:%M"):
    if not iso_string:
        return "?"
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(TZ_NAME)).strftime(fmt)


def wmo_desc(code):
    code = int(code)
    if code == 0:
        return "Clear"
    if code == 1:
        return "Mainly clear"
    if code == 2:
        return "Part cloudy"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if code in (51, 53, 55):
        return "Drizzle"
    if code in (56, 57):
        return "Frz drizzle"
    if code in (61, 63, 65):
        return "Rain"
    if code in (66, 67):
        return "Frz rain"
    if code in (71, 73, 75):
        return "Snow"
    if code == 77:
        return "Snow grains"
    if code in (80, 81, 82):
        return "Showers"
    if code in (85, 86):
        return "Snow showers"
    if code == 95:
        return "Thunderstorm"
    if code in (96, 99):
        return "Thunder/hail"
    return "Unknown"


def weather_icon_url(code):
    """Map WMO weather code to local icon image."""
    code = int(code)
    
    # Use the generated PNG for this WMO code
    icon_filename = f"code_{code:02d}.png"
    icon_path = os.path.join(ICON_DIR, icon_filename)
    
    return icon_path if os.path.exists(icon_path) else None


def get_weather_icon_image(code, size=24):
    """Get weather icon image, download if needed, and resize to specified size."""
    icon_path = weather_icon_url(code)
    if not icon_path or not os.path.exists(icon_path):
        return None
    
    try:
        icon = Image.open(icon_path).convert("RGBA")
        icon = icon.resize((size, size), Image.LANCZOS)
        # Composite onto white so the L result has clean dark-on-white pixels
        bg = Image.new("RGBA", (size, size), (255, 255, 255, 255))
        bg.paste(icon, (0, 0), icon)
        return bg.convert("L")
    except Exception as e:
        print(f"Failed to load weather icon: {e}")
        return None


def weather_icon(draw, x, y, size, code):
    radius = size // 2
    cx = x + radius
    cy = y + radius
    if code in (0, 1):
        draw.ellipse((x, y, x + size, y + size), outline=0, width=2)
        draw.line((cx, y + 4, cx, y + size - 4), fill=0, width=2)
        draw.line((x + 4, cy, x + size - 4, cy), fill=0, width=2)
    elif code in (2, 3, 45, 48):
        draw.rectangle((x + 4, y + size * 0.3, x + size - 4, y + size * 0.65), outline=0, width=2)
        draw.arc((x + 2, y + size * 0.1, x + size - 2, y + size * 0.7), 0, 180, fill=0, width=2)
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        draw.rectangle((x + 4, y + size * 0.2, x + size - 4, y + size * 0.6), outline=0, width=2)
        for i in range(3):
            sx = x + 6 + i * 8
            draw.line((sx, y + size * 0.65, sx, y + size - 4), fill=0, width=2)
    elif code in (56, 57, 66, 67):
        draw.rectangle((x + 4, y + size * 0.2, x + size - 4, y + size * 0.55), outline=0, width=2)
        for i in range(2):
            sx = x + 8 + i * 12
            draw.line((sx, y + size * 0.55, sx, y + size - 4), fill=0, width=2)
    elif code in (71, 73, 75, 77, 85, 86):
        draw.rectangle((x + 4, y + size * 0.25, x + size - 4, y + size * 0.55), outline=0, width=2)
        for i in range(3):
            strike_x = x + 6 + i * 8
            draw.line((strike_x, y + size * 0.55, strike_x + 4, y + size - 4), fill=0, width=2)
    elif code in (95, 96, 99):
        draw.polygon([
            (cx, y + 4),
            (x + 4, y + size * 0.57),
            (cx - 4, y + size * 0.4),
            (x + size - 4, y + size - 4),
            (cx + 4, y + size * 0.4),
        ], outline=0, fill=None)
    else:
        draw.rectangle((x + 4, y + 4, x + size - 4, y + size - 4), outline=0, width=2)


def fetch_json(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        return None


def build_price_graph(prices, target_width=772, target_height=260, font_path=None):
    if not prices:
        return None

    if font_path:
        try:
            from matplotlib import font_manager as fm
            fm.fontManager.addfont(font_path)
            prop = fm.FontProperties(fname=font_path)
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [prop.get_name()] + matplotlib.rcParams.get("font.sans-serif", [])
        except Exception:
            pass

    times = [iso_to_local(slot[0], "%H:%M") for slot in prices]
    values = [slot[1] for slot in prices]
    x = list(range(len(times)))
    # Tick on every even hour (30-min slots → every 4 slots = 2 h)
    tick_idx = [i for i, t in enumerate(times) if t.endswith(":00") and int(t[:2]) % 2 == 0]
    if not tick_idx:
        tick_idx = x[::max(1, len(x) // 8)]

    fig, ax = plt.subplots(figsize=(target_width / 100, target_height / 100), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    floor = min(0, min(values))
    ax.plot(x, values, color="black", linewidth=1.5)
    ax.fill_between(x, values, floor, color="black", alpha=0.1)
    ax.set_ylim(bottom=floor)
    ax.set_ylabel("p/kWh", fontsize=9)
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([times[i] for i in tick_idx], rotation=45, fontsize=8)
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(True, color="black", linestyle=":", linewidth=0.5)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    graph = Image.open(buf).convert("L")
    if graph.size != (target_width, target_height):
        graph = graph.resize((target_width, target_height), resample=Image.LANCZOS)
    return graph


def build_rain_chart(times, probs, target_width=304, target_height=260, font_path=None):
    if not times or not probs:
        return None

    if font_path:
        try:
            from matplotlib import font_manager as fm
            fm.fontManager.addfont(font_path)
            prop = fm.FontProperties(fname=font_path)
            matplotlib.rcParams["font.family"] = "sans-serif"
            matplotlib.rcParams["font.sans-serif"] = [prop.get_name()] + matplotlib.rcParams.get("font.sans-serif", [])
        except Exception:
            pass

    n = min(24, len(times))
    labels = [t[11:16] for t in times[:n]]  # "HH:MM" from "YYYY-MM-DDTHH:MM"
    values = probs[:n]
    x = list(range(n))
    # Tick on every even hour (hourly data → every 2 indices)
    tick_idx = [i for i, l in enumerate(labels) if int(l[:2]) % 2 == 0]
    if not tick_idx:
        tick_idx = x[::2]

    fig, ax = plt.subplots(figsize=(target_width / 100, target_height / 100), dpi=100)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(x, values, color="black", linewidth=1.5)
    ax.fill_between(x, values, 0, color="black", alpha=0.1)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Rain %", fontsize=9)
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([labels[i] for i in tick_idx], rotation=45, fontsize=8)
    ax.tick_params(axis="y", labelsize=9)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.grid(True, color="black", linestyle=":", linewidth=0.5, axis="y")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    chart = Image.open(buf).convert("L")
    if chart.size != (target_width, target_height):
        chart = chart.resize((target_width, target_height), resample=Image.LANCZOS)
    return chart


def generate_dashboard_image():
    image = Image.new("L", (WIDTH, HEIGHT), color=255)
    draw = ImageDraw.Draw(image)
    font_path = find_font_path()
    font_regular = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default()
    font_small = ImageFont.truetype(font_path, 14) if font_path else ImageFont.load_default()

    # Column x positions (pixels) for weather table
    WX_DAY   = 34
    WX_DATE  = 80
    WX_COND  = 128
    WX_HILO  = 228
    WX_RAIN  = 302

    draw.text((14, 10), "Oxford weather", font=font_regular, fill=0)
    draw.text((WX_DAY,  32), "Day",   font=font_small, fill=0)
    draw.text((WX_DATE, 32), "Date",  font=font_small, fill=0)
    draw.text((WX_COND, 32), "Conditions", font=font_small, fill=0)
    draw.text((WX_HILO, 32), "Hi/Lo", font=font_small, fill=0)
    draw.text((WX_RAIN, 32), "Rain",  font=font_small, fill=0)

    weather_data = fetch_json(WEATHER_URL)
    hourly_times, hourly_probs = [], []
    if weather_data and "daily" in weather_data:
        daily = weather_data["daily"]
        ICON_SIZE = 24
        icon_y_off = (WEATHER_ROW_HEIGHT - ICON_SIZE) // 2   # centres 24px icon in 33px row
        text_y_off = (WEATHER_ROW_HEIGHT - 17) // 2          # centres ~17px text in 33px row
        for idx in range(min(WEATHER_ROWS, len(daily.get("time", [])))):
            y = TOP_MARGIN + idx * WEATHER_ROW_HEIGHT
            date = daily["time"][idx]
            code = daily["weathercode"][idx]
            hi = round(daily["temperature_2m_max"][idx])
            lo = round(daily["temperature_2m_min"][idx])
            rain = daily["precipitation_probability_max"][idx]
            dow = iso_to_local(date + "T00:00:00Z", "%a")
            short_date = datetime.fromisoformat(date + "T00:00:00+00:00").strftime("%d/%m")
            desc = wmo_desc(code)

            icon_img = get_weather_icon_image(code, ICON_SIZE)
            if icon_img:
                image.paste(icon_img, (8, y + icon_y_off))
            else:
                weather_icon(draw, 8, y + icon_y_off, ICON_SIZE, code)

            draw.text((WX_DAY,  y + text_y_off), dow,          font=font_small, fill=0)
            draw.text((WX_DATE, y + text_y_off), short_date,    font=font_small, fill=0)
            draw.text((WX_COND, y + text_y_off), desc,          font=font_small, fill=0)
            draw.text((WX_HILO, y + text_y_off), f"{hi}/{lo}°C", font=font_small, fill=0)
            draw.text((WX_RAIN, y + text_y_off), f"{rain}%",    font=font_small, fill=0)

        if "hourly" in weather_data:
            now_naive = datetime.now(ZoneInfo(TZ_NAME)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
            for t, p in zip(weather_data["hourly"]["time"], weather_data["hourly"]["precipitation_probability"]):
                if datetime.fromisoformat(t) >= now_naive:
                    hourly_times.append(t)
                    hourly_probs.append(p)
            hourly_times = hourly_times[:24]
            hourly_probs = hourly_probs[:24]

        # Rain chart on the right of the weather table, aligned with header row
        RAIN_CHART_X = 334
        RAIN_CHART_Y = 32
        rain_chart_w = WIDTH - 14 - RAIN_CHART_X
        rain_chart_h = TOP_MARGIN + WEATHER_ROWS * WEATHER_ROW_HEIGHT - RAIN_CHART_Y
        rain_chart = build_rain_chart(hourly_times, hourly_probs, rain_chart_w, rain_chart_h, font_path)
        if rain_chart:
            image.paste(rain_chart, (RAIN_CHART_X, RAIN_CHART_Y))
    else:
        draw.text((14, 80), "Weather fetch failed", font=font_regular, fill=0)

    divider_y = TOP_MARGIN + WEATHER_ROWS * WEATHER_ROW_HEIGHT + 16
    draw.line((10, divider_y, WIDTH - 10, divider_y), fill=0, width=2)
    draw.text((14, divider_y + 8), "Octopus Agile", font=font_regular, fill=0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    octopus_url = OCTOPUS_URL_TEMPLATE.format(product=OCTOPUS_PRODUCT, tariff=OCTOPUS_TARIFF, period_from=now)
    octopus_data = fetch_json(octopus_url)

    if octopus_data and "results" in octopus_data:
        now_dt = datetime.now(timezone.utc)
        slots = sorted(
            [(slot["valid_from"], slot["value_inc_vat"]) for slot in octopus_data["results"]
             if datetime.fromisoformat(slot["valid_from"].replace("Z", "+00:00")) >= now_dt],
            key=lambda item: item[0],
        )
        if slots:
            prices = slots
            # x column where time ranges start (after the longest label "Most expensive 2h:")
            ELEC_TIME_X = 160
            if len(prices) >= 8:
                window_4h = min(
                    (
                        (i, sum(value for _, value in prices[i : i + 8]) / 8)
                        for i in range(len(prices) - 7)
                    ),
                    key=lambda item: item[1],
                )
                win_start, win_avg = prices[window_4h[0]][0], window_4h[1]
                win_start_local = iso_to_local(win_start, "%a %H:%M")
                win_end_local = iso_to_local(prices[window_4h[0] + 8][0], "%H:%M") if window_4h[0] + 8 < len(prices) else "?"
                draw.text((14, divider_y + 34), "Cheapest 4h:", font=font_small, fill=0)
                draw.text((ELEC_TIME_X, divider_y + 34), f"{win_start_local} - {win_end_local}  (avg {win_avg:.1f} p/kWh)", font=font_small, fill=0)
            if len(prices) >= 4:
                window_2h = max(
                    (
                        (i, sum(value for _, value in prices[i : i + 4]) / 4)
                        for i in range(len(prices) - 3)
                    ),
                    key=lambda item: item[1],
                )
                exp_start, exp_avg = prices[window_2h[0]][0], window_2h[1]
                exp_start_local = iso_to_local(exp_start, "%a %H:%M")
                exp_end_local = iso_to_local(prices[window_2h[0] + 4][0], "%H:%M") if window_2h[0] + 4 < len(prices) else "?"
                draw.text((14, divider_y + 54), "Most expensive 2h:", font=font_small, fill=0)
                draw.text((ELEC_TIME_X, divider_y + 54), f"{exp_start_local} - {exp_end_local}  (avg {exp_avg:.1f} p/kWh)", font=font_small, fill=0)

            graph_y = divider_y + 78
            graph_w = WIDTH - 28
            graph_h = HEIGHT - graph_y - 10
            price_graph = build_price_graph(prices, graph_w, graph_h, font_path)
            if price_graph:
                image.paste(price_graph, (14, graph_y))
        else:
            draw.text((14, divider_y + 34), "No price data yet", font=font_regular, fill=0)
    else:
        draw.text((14, divider_y + 34), "Electricity fetch failed", font=font_regular, fill=0)

    footer_text = f"Updated: {datetime.now(ZoneInfo(TZ_NAME)).strftime('%a %d %b %H:%M %Z')}"
    draw.text((14, HEIGHT - 22), footer_text, font=font_small, fill=0)
    return image


@app.route("/")
def index():
    return render_template_string(
        "<html><body><h2>Kindle Dashboard</h2><p><img src=\"/dashboard.png\" alt=\"dashboard\"/></p></body></html>"
    )


@app.route("/dashboard.png")
def dashboard_png():
    img = generate_dashboard_image()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.read(), mimetype="image/png")


@app.route("/health")
def health():
    return "ok\n"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

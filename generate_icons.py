#!/usr/bin/env python3
"""Convert vendored weather-icons SVGs to monochrome PNGs for Kindle display."""
import os
import subprocess

ICON_DIR = os.path.join(os.path.dirname(__file__), "weather_icons")
SVG_DIR = os.path.join(os.path.dirname(__file__), "weather-icons", "svg")
SIZE = 64

# Map WMO codes to weather-icons SVG filenames
ICON_MAP = {
    0: "wi-day-sunny.svg",           # Clear
    1: "wi-day-sunny-overcast.svg",  # Mainly clear
    2: "wi-day-cloudy.svg",          # Part cloudy
    3: "wi-cloudy.svg",              # Overcast
    45: "wi-fog.svg",                # Fog
    48: "wi-fog.svg",                # Fog
    51: "wi-day-sprinkle.svg",       # Drizzle
    53: "wi-day-sprinkle.svg",       # Drizzle
    55: "wi-day-rain.svg",           # Drizzle
    56: "wi-day-rain-mix.svg",       # Freezing drizzle
    57: "wi-day-rain-mix.svg",       # Freezing drizzle
    61: "wi-day-rain.svg",           # Rain
    63: "wi-day-rain.svg",           # Rain
    65: "wi-day-rain.svg",           # Rain
    66: "wi-day-rain-mix.svg",       # Freezing rain
    67: "wi-day-rain-mix.svg",       # Freezing rain
    71: "wi-day-snow.svg",           # Snow
    73: "wi-day-snow.svg",           # Snow
    75: "wi-day-snow.svg",           # Snow
    77: "wi-day-snow.svg",           # Snow grains
    80: "wi-day-showers.svg",        # Showers
    81: "wi-day-showers.svg",        # Showers
    82: "wi-day-showers.svg",        # Showers
    85: "wi-day-snow.svg",           # Snow showers
    86: "wi-day-snow.svg",           # Snow showers
    95: "wi-day-thunderstorm.svg",   # Thunderstorm
    96: "wi-day-snow-thunderstorm.svg",  # Thunder/hail
    99: "wi-day-snow-thunderstorm.svg",  # Thunder/hail
}

def convert_svg_to_png(svg_path, output_path, size=SIZE):
    """Convert SVG to grayscale PNG using ImageMagick."""
    try:
        # Convert SVG to PNG with size, then convert to grayscale for Kindle
        cmd = [
            "convert",
            f"{svg_path}",
            "-background", "white",
            "-flatten",
            "-resize", f"{size}x{size}",
            "-colorspace", "Gray",
            f"{output_path}"
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error converting {svg_path}: {e}")
        return False

def generate_icons():
    """Generate PNG icons from vendored SVGs."""
    os.makedirs(ICON_DIR, exist_ok=True)
    
    # Generate for all common WMO codes
    for code, svg_filename in ICON_MAP.items():
        svg_path = os.path.join(SVG_DIR, svg_filename)
        if not os.path.exists(svg_path):
            print(f"Warning: {svg_filename} not found at {svg_path}")
            continue
        
        # Create a simple icon name based on code
        png_filename = f"code_{code:02d}.png"
        png_path = os.path.join(ICON_DIR, png_filename)
        
        if convert_svg_to_png(svg_path, png_path):
            print(f"Created {png_filename} from {svg_filename}")
        else:
            print(f"Failed to create {png_filename}")
    
    print("Icon generation complete!")

if __name__ == "__main__":
    generate_icons()

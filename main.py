#!/usr/bin/env python3
from app import generate_dashboard_image

img = generate_dashboard_image()
img.save("dashboard.png")
print("Saved dashboard.png")

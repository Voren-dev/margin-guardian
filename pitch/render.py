"""Renders the slides and the video title cards with headless Chromium.

    python3 render.py   ->  margin-guardian-pitch.pdf, preview/<n>.png, preview/cards/<n>.png
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SIZE = {"width": 1920, "height": 1080}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport=SIZE)
    for source, out in (("slides.html", HERE / "preview"), ("cards.html", HERE / "preview" / "cards")):
        out.mkdir(parents=True, exist_ok=True)
        page.goto((HERE / source).as_uri())
        page.wait_for_timeout(1500)  # the fonts
        if source == "slides.html":
            page.pdf(path=str(HERE / "margin-guardian-pitch.pdf"), width="1920px", height="1080px", print_background=True)
        for number in range(page.locator("section").count()):
            page.locator("section").nth(number).screenshot(path=str(out / f"{number + 1}.png"))
    browser.close()
print("slides and cards rendered")

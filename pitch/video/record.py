"""Records the app on margin.voren.dev for the demo video, one scene per file.

A fake pointer is drawn on the page (headless Chromium shows none) and glides to each
element before the click, so the viewer can follow what happens.

Not Playwright's video recorder (low bitrate, blurry): Chromium's screencast sends a
frame each time the page changes, as a JPEG at quality 95, rendered at 1920x1080 from a
1440x810 layout (device scale 4/3), so the text is bigger and sharp. The frames keep
their timestamps and ffmpeg turns them into a 30 fps video.
"""
import base64
import json
import time
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SITE = "https://margin.voren.dev"
SIZE = {"width": 1440, "height": 810}  # the layout; drawn at 4/3 scale, so 1920x1080 in the video
SCALE = 4 / 3
READ = 1.6  # every pause is this much longer than the bare minimum, so a viewer can read

POINTER = """
(() => { if (document.getElementById('fake-pointer')) return;
  const c = document.createElement('div'); c.id = 'fake-pointer';
  c.style.cssText = 'position:fixed;left:720px;top:520px;width:26px;height:26px;border-radius:50%;'
    + 'background:rgba(255,184,77,.85);border:3px solid #F1EBDD;z-index:999999;pointer-events:none;'
    + 'transform:translate(-50%,-50%);transition:left .7s ease,top .7s ease,transform .15s;box-shadow:0 2px 10px rgba(0,0,0,.4)';
  document.body.appendChild(c); })()
"""


MARKS = {}  # moment name -> wall clock time, to cut the video in assemble.py


def mark(name):
    MARKS[name] = time.time()


def pause(page, ms):
    page.wait_for_timeout(int(ms * READ))


def glide(page, locator, click=True):
    box = locator.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.evaluate(POINTER)
    page.evaluate(f"(() => {{ const c = document.getElementById('fake-pointer'); c.style.left = '{x}px'; c.style.top = '{y}px'; }})()")
    page.wait_for_timeout(900)  # the pointer glides in 0.7 s
    if click:
        page.evaluate("document.getElementById('fake-pointer').style.transform = 'translate(-50%,-50%) scale(.7)'")
        page.wait_for_timeout(150)
        locator.click()
        page.evaluate("document.getElementById('fake-pointer').style.transform = 'translate(-50%,-50%)'")


def scroll(page, y, wait=1200):
    page.locator('[data-testid="stMain"]').evaluate(f"e => e.scrollTo({{top: {y}, behavior: 'smooth'}})")
    pause(page, wait)


def scene_ciclo(page):
    page.goto(SITE, wait_until="networkidle"); pause(page, 2500)
    page.evaluate(POINTER); pause(page, 800)
    mark("start")
    glide(page, page.get_by_role("button", name="Check this price list").nth(1))
    pause(page, 9000)  # the steps, then the count-up and the hidden changes
    mark("footnote")
    glide(page, page.get_by_role("tab", name="The price list")); pause(page, 1500)
    scroll(page, 430, 3500)
    mark("moves")
    glide(page, page.get_by_role("tab", name="What to do")); pause(page, 3500)
    mark("email")
    glide(page, page.get_by_role("tab", name="Email to the supplier")); pause(page, 2500)
    scroll(page, 700, 4000)


def scene_trailgear(page):
    page.goto(SITE, wait_until="networkidle"); pause(page, 2500)
    page.evaluate(POINTER); pause(page, 500)
    mark("start")
    glide(page, page.get_by_role("button", name="TrailGear Ltd · 6 changes"))
    pause(page, 5000)
    mark("detail")
    glide(page, page.get_by_role("button", name="Show me").first)
    pause(page, 3500)
    scroll(page, 330, 3500)
    scroll(page, 760, 3500)


def scene_photo(page):
    page.goto(SITE, wait_until="networkidle"); pause(page, 2500)
    page.evaluate(POINTER); pause(page, 500)
    mark("start")
    glide(page, page.locator('[data-testid="stFileUploaderDropzone"]'), click=False)
    page.locator('input[type="file"]').set_input_files(str(HERE / "ciclo-photo.jpg"))
    mark("reading")
    page.locator("text=Read the photo").wait_for(timeout=400_000)  # the first step: the reading is done
    mark("read")
    page.wait_for_url("**/supplier", timeout=60_000)
    pause(page, 6000)
    glide(page, page.get_by_role("tab", name="The price list")); pause(page, 1500)
    scroll(page, 420, 4000)


SCENES = {"ciclo": scene_ciclo, "trailgear": scene_trailgear, "photo": scene_photo}

def record(name):
    frames_dir = HERE / "rec" / name
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True)
    frames = []  # (timestamp, file)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport=SIZE, device_scale_factor=SCALE)
        page = context.new_page()
        cdp = context.new_cdp_session(page)

        def on_frame(event):
            path = frames_dir / f"{len(frames):05d}.jpg"
            path.write_bytes(base64.b64decode(event["data"]))
            frames.append((event["metadata"]["timestamp"], path))
            cdp.send("Page.screencastFrameAck", {"sessionId": event["sessionId"]})

        cdp.on("Page.screencastFrame", on_frame)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 95, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        SCENES[name](page)
        page.wait_for_timeout(300)
        cdp.send("Page.stopScreencast")
        end = frames[-1][0] + 0.5
        marks = {key: round(value - frames[0][0], 2) for key, value in MARKS.items()}
        marks["end"] = round(end - frames[0][0], 2)
        (HERE / "rec" / f"{name}.json").write_text(json.dumps(marks))
        MARKS.clear()
        context.close()
        browser.close()

    # each frame lasts until the next one; ffmpeg makes a constant 30 fps out of it
    lines = []
    for (stamp, path), following in zip(frames, [f[0] for f in frames[1:]] + [end]):
        lines.append(f"file '{path}'\nduration {max(following - stamp, 0.001):.4f}\n")
    lines.append(f"file '{frames[-1][1]}'\n")
    listing = frames_dir / "frames.txt"
    listing.write_text("".join(lines))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "14",
                    str(HERE / "rec" / f"{name}.mp4")], check=True)
    shutil.rmtree(frames_dir)
    print(name, "recorded", f"{end - frames[0][0]:.1f} s", len(frames), "frames")


for name in sys.argv[1:] or SCENES:
    record(name)

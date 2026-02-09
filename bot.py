import os
import io
import random
import datetime
import requests
from PIL import Image
from atproto import Client

common_resolutions = [
    (1920, 1080),  # 16:9 (FHD)
    (1280, 720),   # 16:9 (HD)
    (1024, 768),   # 4:3
    (600, 800),    # 3:4 (Portrait)
    (800, 600),    # 4:3 (Landscape)
    (800, 800),    # 1:1 (Square)
    (1600, 900)    # 16:9
]

PICSUM_BASE = "https://picsum.photos"
MAX_BYTES = 1_000_000
TARGET_MAX_BYTES = 950_000  # leave some safety margin


def download_random_picsum(width: int, height: int, timeout_s: int = 30) -> tuple[bytes, str]:
    """
    Downloads a random image from Picsum at the requested resolution.
    Picsum typically redirects to a specific image URL; we keep the final URL for attribution.
    """
    url = f"{PICSUM_BASE}/{width}/{height}"
    resp = requests.get(url, timeout=timeout_s, allow_redirects=True)
    resp.raise_for_status()
    final_url = resp.url
    return resp.content, final_url


def convert_and_compress_to_jpeg(img_bytes: bytes, width: int, height: int) -> bytes:
    """
    Converts to RGB JPEG, resizes to exact dimensions, and compresses until under limit.
    Re-saving strips metadata, which Bluesky recommends. :contentReference[oaicite:3]{index=3}
    """
    img = Image.open(io.BytesIO(img_bytes))

    # Ensure exact size and consistent output
    img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height), Image.LANCZOS)

    # Try decreasing quality until it fits
    for quality in [95, 92, 90, 88, 85, 82, 80, 78, 75, 72, 70, 65, 60, 55, 50]:
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        data = out.getvalue()
        if len(data) <= TARGET_MAX_BYTES:
            return data

    # As a last resort, scale down slightly and try again
    scale = 0.9
    for _ in range(5):
        new_w = max(1, int(width * scale))
        new_h = max(1, int(height * scale))
        tmp = img.resize((new_w, new_h), Image.LANCZOS)
        for quality in [80, 75, 70, 65, 60, 55]:
            out = io.BytesIO()
            tmp.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
            data = out.getvalue()
            if len(data) <= TARGET_MAX_BYTES:
                return data
        scale *= 0.9

    raise RuntimeError("Could not compress image under the size limit.")


def main():
    handle = os.environ.get("BSKY_HANDLE", "").strip()
    app_password = os.environ.get("BSKY_APP_PASSWORD", "").strip()
    pds = os.environ.get("BSKY_PDS", "").strip()  # optional, usually empty

    if not handle or not app_password:
        raise RuntimeError("Missing BSKY_HANDLE or BSKY_APP_PASSWORD environment variables.")

    width, height = random.choice(common_resolutions)

    raw_bytes, final_url = download_random_picsum(width, height)
    jpeg_bytes = convert_and_compress_to_jpeg(raw_bytes, width, height)

    if len(jpeg_bytes) > MAX_BYTES:
        raise RuntimeError(f"Image is still too large: {len(jpeg_bytes)} bytes")

    client = Client(pds) if pds else Client()
    client.login(handle, app_password)

    today_utc = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    text = f"Daily random image {today_utc}\n{width}x{height}\nSource: {final_url}"
    alt = f"Random photo placeholder at {width} by {height} resolution."

    # atproto SDK includes a high-level helper for image posts. :contentReference[oaicite:4]{index=4}
    client.send_image(text=text, image=jpeg_bytes, image_alt=alt)

    print("Posted successfully:", width, height, final_url, "bytes:", len(jpeg_bytes))


if __name__ == "__main__":
    main()

"""Network interceptor — captures all XHR/Fetch calls from a platform to discover API endpoints.

Usage:
    python scraper/network_interceptor.py --platform ubereats
    python scraper/network_interceptor.py --platform rappi
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent

ADDRESS = "Álvaro Obregón 311, Roma Norte, Ciudad de México"
LAT = 19.4165
LNG = -99.1653

PLATFORM_URLS = {
    "ubereats": "https://www.ubereats.com/mx",
    "rappi": "https://www.rappi.com.mx",
}

# Filters — endpoints we don't care about (analytics, fonts, images)
SKIP_PATTERNS = [
    r"\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|css)(\?|$)",
    r"analytics|segment|mixpanel|sentry|datadog|amplitude|hotjar|gtm|google-analytics",
    r"fonts\.googleapis|cloudfront\.net/static",
]


def should_skip(url: str) -> bool:
    return any(re.search(p, url, re.IGNORECASE) for p in SKIP_PATTERNS)


def is_interesting(url: str) -> bool:
    """Flag endpoints that likely carry restaurant/product/fee data."""
    patterns = [
        r"restaurant|store|menu|feed|listing|search|catalog",
        r"fee|price|delivery|fulfillment|surge|eta",
        r"graphql|api/v\d|/api/",
        r"eats\.uber|rappi\.com.*api",
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)


def intercept(platform: str, headless: bool = False, wait_seconds: int = 45) -> list[dict]:
    """Open the platform in a browser, navigate to the address, capture network calls.

    Args:
        platform: "ubereats" or "rappi"
        headless: Run browser visibly (False) so you can interact manually
        wait_seconds: How long to wait for network traffic after page load

    Returns:
        List of captured request dicts with url, method, headers, response body.
    """
    from playwright.sync_api import sync_playwright

    base_url = PLATFORM_URLS[platform]
    captured: list[dict] = []

    print(f"\n[*] Opening {platform} at {base_url}")
    print(f"[*] Will capture network for {wait_seconds}s after page load")
    print(f"[*] Target address: {ADDRESS}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="es-MX",
            geolocation={"latitude": LAT, "longitude": LNG},
            permissions=["geolocation"],
        )

        page = context.new_page()

        # ── Intercept all requests ──────────────────────────────────────────
        def on_request(request):
            url = request.url
            if should_skip(url):
                return
            captured.append({
                "type": "request",
                "method": request.method,
                "url": url,
                "headers": dict(request.headers),
                "post_data": request.post_data,
                "interesting": is_interesting(url),
            })

        def on_response(response):
            url = response.url
            if should_skip(url) or not is_interesting(url):
                return
            try:
                body = response.body()
                # Only keep JSON responses
                ct = response.headers.get("content-type", "")
                if "json" in ct or body[:1] in (b"{", b"["):
                    try:
                        parsed = json.loads(body)
                    except Exception:
                        parsed = body.decode("utf-8", errors="replace")[:2000]
                    captured.append({
                        "type": "response",
                        "url": url,
                        "status": response.status,
                        "content_type": ct,
                        "body_preview": parsed if isinstance(parsed, str) else json.dumps(parsed)[:3000],
                        "interesting": True,
                    })
                    print(f"  [JSON] {response.status} {url[:100]}")
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        # ── Navigate and wait ───────────────────────────────────────────────
        page.goto(base_url, timeout=30_000, wait_until="domcontentloaded")
        print(f"[*] Page loaded. Waiting {wait_seconds}s for network calls...")
        print(f"[*] Manually change address to: {ADDRESS}")
        print(f"[*] Then browse to McDonald's or Burger King\n")

        # Auto-attempt address via URL for Uber Eats (lat/lng in URL)
        if platform == "ubereats":
            # Uber Eats accepts lat/lng in the URL for feed
            feed_url = (
                f"https://www.ubereats.com/mx/feed"
                f"?diningMode=DELIVERY"
                f"&pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMiVDMyVBMWx2YXJvJTIwT2JyZWclQzMlQjNuJTIwMzExJTIyJTJDJTIybGF0aXR1ZGUlMjIlM0ExOS40MTY1JTJDJTIybG9uZ2l0dWRlJTIyJTNBLTk5LjE2NTMlN0Q%3D"
            )
            print(f"[*] Trying direct feed URL with coordinates...")
            page.goto(feed_url, timeout=30_000, wait_until="domcontentloaded")

        time.sleep(wait_seconds)
        context.close()
        browser.close()

    return captured


def analyze_and_report(captured: list[dict], platform: str) -> None:
    """Print analysis of captured calls and save full log to JSON."""
    requests = [c for c in captured if c["type"] == "request"]
    responses = [c for c in captured if c["type"] == "response"]
    interesting_req = [r for r in requests if r.get("interesting")]

    print("\n" + "=" * 70)
    print(f"NETWORK INTERCEPTION REPORT — {platform.upper()}")
    print("=" * 70)
    print(f"Total requests captured: {len(requests)}")
    print(f"Interesting requests:    {len(interesting_req)}")
    print(f"JSON responses captured: {len(responses)}")

    print("\n--- INTERESTING API ENDPOINTS ---")
    seen = set()
    for r in interesting_req:
        url = r["url"]
        # Deduplicate by stripping query params for display
        base = url.split("?")[0]
        if base not in seen:
            seen.add(base)
            print(f"  [{r['method']}] {url[:120]}")

    print("\n--- JSON RESPONSES (first 3) ---")
    for resp in responses[:3]:
        print(f"\n  URL: {resp['url'][:100]}")
        print(f"  Status: {resp['status']}")
        preview = resp.get("body_preview", "")
        if isinstance(preview, str):
            print(f"  Body preview: {preview[:500]}")

    # Save full log
    out_path = ROOT / "data" / "raw" / f"network_log_{platform}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(captured, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[*] Full log saved: {out_path}")
    print("[*] Open the log to find the exact endpoint + headers to hardcode in the scraper.\n")


def main():
    parser = argparse.ArgumentParser(description="Network interceptor for delivery platforms")
    parser.add_argument("--platform", choices=["ubereats", "rappi", "didifood"], default="ubereats")
    parser.add_argument("--headless", action="store_true", help="Run browser headless (default: visible)")
    parser.add_argument("--wait", type=int, default=45, help="Seconds to capture after page load")
    args = parser.parse_args()

    captured = intercept(args.platform, headless=args.headless, wait_seconds=args.wait)
    analyze_and_report(captured, args.platform)


if __name__ == "__main__":
    main()

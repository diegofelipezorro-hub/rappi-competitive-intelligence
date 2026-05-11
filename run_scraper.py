"""Entry point for the Rappi Competitive Intelligence scraping pipeline.

Usage examples:
    python run_scraper.py                       # Full scrape (uses SCRAPING_MODE from .env)
    python run_scraper.py --mode mock           # Force mock mode
    python run_scraper.py --mode production     # Force production mode
    python run_scraper.py --cities cdmx         # Only CDMX addresses
    python run_scraper.py --generate-report     # Scrape + generate HTML report
    python run_scraper.py --addresses 5         # Only first N addresses (for testing)
"""

import argparse
import datetime
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# ── Logging setup ─────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_scraper")


def load_config() -> tuple[list[dict], list[dict]]:
    """Load addresses and products from config JSON files."""
    with open(ROOT / "config" / "addresses.json", encoding="utf-8") as f:
        addresses = json.load(f)["addresses"]
    with open(ROOT / "config" / "products.json", encoding="utf-8") as f:
        products_raw = json.load(f)
    # Flatten all product categories into a single list
    products = []
    for category_items in products_raw.values():
        products.extend(category_items)
    return addresses, products


def run_mock(addresses: list[dict], products: list[dict]) -> list[dict]:
    """Generate synthetic data using the mock data generator."""
    from scraper.mock_data_generator import generate_mock_dataset
    logger.info("Running in MOCK mode — generating synthetic data")
    return generate_mock_dataset(addresses, products)


def run_production(addresses: list[dict], products: list[dict]) -> list[dict]:
    """Run real scrapers with automatic fallback to mock on failure.

    Known limitations (documented as blockers):
    - DiDi Food Mexico has no public web ordering interface — app only.
      Uses mock_fallback data for DiDi to keep dataset complete.
    - Rappi/Uber Eats Playwright scrapers connect successfully but CSS selectors
      need discovery via DevTools inspection of live pages. Currently return
      unavailable status; mock_fallback fills the gap.
    """
    from scraper.rappi_scraper import RappiScraper
    from scraper.ubereats_scraper import UberEatsScraper
    from scraper.mock_data_generator import generate_mock_dataset

    # DiDi Food: app-only, no web scraping possible — always use mock
    logger.warning(
        "[didifood] DiDi Food Mexico has no public web interface. "
        "Using realistic mock data for DiDi. Rappi/Uber Eats use live Playwright."
    )

    scrapers = {
        "rappi": RappiScraper(),
        "ubereats": UberEatsScraper(),
    }

    all_records: list[dict] = []
    for address in addresses:
        # Scrape Rappi and Uber Eats with real Playwright
        for platform, scraper in scrapers.items():
            try:
                records = scraper.scrape_with_retry(address, products)
                # If scraper connected but found no prices (selectors need tuning),
                # fall back to mock so the dataset stays complete
                real_success = [r for r in records if r.get("scraping_status") == "success"]
                if not real_success:
                    logger.warning(
                        "[%s] Connected to site but no prices extracted for %s — "
                        "CSS selectors need tuning for live site. Using mock_fallback.",
                        platform, address.get("id"),
                    )
                    fallback = generate_mock_dataset([address], products, platforms=[platform])
                    for r in fallback:
                        r["scraping_mode"] = "mock_fallback"
                    all_records.extend(fallback)
                else:
                    all_records.extend(records)
            except Exception as exc:
                logger.error("[%s] Fatal failure for %s: %s — using mock fallback", platform, address.get("id"), exc)
                fallback = generate_mock_dataset([address], products, platforms=[platform])
                for r in fallback:
                    r["scraping_mode"] = "mock_fallback"
                all_records.extend(fallback)

        # DiDi Food: always mock (app-only platform)
        didi_fallback = generate_mock_dataset([address], products, platforms=["didifood"])
        for r in didi_fallback:
            r["scraping_mode"] = "mock_fallback"
        all_records.extend(didi_fallback)

    return all_records


def save_data(records: list[dict], timestamp: str) -> tuple[str, str]:
    """Save records as JSON (raw) and CSV (processed). Returns (json_path, csv_path)."""
    raw_dir = ROOT / "data" / "raw"
    processed_dir = ROOT / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    json_path = raw_dir / f"competitive_data_{timestamp}.json"
    csv_path = processed_dir / f"competitive_data_{timestamp}.csv"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False, encoding="utf-8")

    return str(json_path), str(csv_path)


def print_summary(records: list[dict]) -> None:
    """Print a final scraping summary to stdout."""
    import sys
    total = len(records)
    success = sum(1 for r in records if r.get("scraping_status") == "success")
    failed = sum(1 for r in records if r.get("scraping_status") == "failed")
    blocked = sum(1 for r in records if r.get("scraping_status") == "blocked")
    unavailable = sum(1 for r in records if r.get("scraping_status") == "unavailable")

    sep = "=" * 60
    lines = [
        f"\n{sep}",
        f"  SCRAPING COMPLETE - {success}/{total} registros exitosos",
        f"  [OK]  Success:     {success:>5}",
        f"  [ERR] Failed:      {failed:>5}",
        f"  [BLK] Blocked:     {blocked:>5}",
        f"  [N/A] Unavailable: {unavailable:>5}",
        f"{sep}\n",
    ]
    output = "\n".join(lines)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rappi Competitive Intelligence Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["mock", "production"],
        default=None,
        help="Override SCRAPING_MODE env var",
    )
    parser.add_argument(
        "--cities",
        nargs="+",
        help="Filter by city (e.g. --cities cdmx guadalajara)",
    )
    parser.add_argument(
        "--addresses",
        type=int,
        default=None,
        metavar="N",
        help="Use only the first N addresses (for testing)",
    )
    parser.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate HTML executive report after scraping",
    )
    args = parser.parse_args()

    # Resolve scraping mode
    mode = args.mode or os.getenv("SCRAPING_MODE", "mock")
    logger.info("Scraping mode: %s", mode.upper())

    addresses, products = load_config()

    # Apply city filter
    if args.cities:
        addresses = [a for a in addresses if a.get("city") in args.cities]
        logger.info("Filtered to cities %s: %d addresses", args.cities, len(addresses))

    # Apply address count limit
    if args.addresses:
        addresses = addresses[: args.addresses]
        logger.info("Limited to first %d addresses", len(addresses))

    logger.info(
        "Starting scrape: %d addresses × 3 platforms × %d products = %d data points",
        len(addresses),
        len(products),
        len(addresses) * 3 * len(products),
    )

    # Run scraping
    try:
        from tqdm import tqdm
        HAS_TQDM = True
    except ImportError:
        HAS_TQDM = False

    if mode == "mock":
        if HAS_TQDM:
            pass  # tqdm shows progress per-item if used
        records = run_mock(addresses, products)
    else:
        records = run_production(addresses, products)

    print_summary(records)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    json_path, csv_path = save_data(records, timestamp)
    logger.info("Raw data saved: %s", json_path)
    logger.info("Processed CSV: %s", csv_path)
    print(f"\n[CSV] Output: {csv_path}")

    # Generate report if requested
    if args.generate_report:
        logger.info("Generating executive HTML report...")
        try:
            import pandas as pd
            from reports.report_generator import generate_report
            df = pd.read_csv(csv_path)
            report_path = generate_report(df)
            print(f"[REPORT] Generated: {report_path}")
        except Exception as exc:
            logger.error("Report generation failed: %s", exc)


if __name__ == "__main__":
    main()

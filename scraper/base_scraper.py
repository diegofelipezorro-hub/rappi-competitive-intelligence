"""Base scraper class with retry logic, rate limiting, and structured logging."""

import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

MAX_RETRIES = 3
MIN_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 5.0


class BaseScraper(ABC):
    """Abstract base class for all platform scrapers.

    Provides rate limiting, retry logic with exponential backoff,
    User-Agent rotation, and structured error handling so individual
    scrapers only need to implement `scrape()`.
    """

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.logger = logging.getLogger(f"{__name__}.{platform}")

    def _random_delay(self) -> None:
        """Sleep a random amount between requests to avoid rate limiting."""
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        self.logger.debug("Rate limit delay: %.1fs", delay)
        time.sleep(delay)

    def _random_user_agent(self) -> str:
        """Return a random realistic User-Agent string."""
        return random.choice(USER_AGENTS)

    def scrape_with_retry(self, address: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Wrap `scrape()` with retry + exponential backoff.

        Returns a list of result dicts; on total failure returns failed-status records
        so the caller never receives an exception.
        """
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._random_delay()
                results = self.scrape(address, products)
                self.logger.info(
                    "[%s] %s — %s: OK (%d records)",
                    self.platform,
                    address.get("city", ""),
                    address.get("address", ""),
                    len(results),
                )
                return results
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                wait = 2**attempt  # 2, 4, 8 seconds
                if attempt < MAX_RETRIES:
                    self.logger.warning(
                        "[%s] Attempt %d/%d failed for %s — retrying in %ds. Error: %s",
                        self.platform,
                        attempt,
                        MAX_RETRIES,
                        address.get("address", ""),
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                else:
                    self.logger.error(
                        "[%s] All %d attempts failed for %s. Error: %s",
                        self.platform,
                        MAX_RETRIES,
                        address.get("address", ""),
                        exc,
                    )

        return self._failed_records(address, products, str(last_error))

    def _failed_records(
        self, address: dict[str, Any], products: list[dict[str, Any]], error_msg: str
    ) -> list[dict[str, Any]]:
        """Generate failed-status placeholder records so the pipeline never breaks."""
        import datetime

        records = []
        for product in products:
            records.append(
                {
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                    "scraping_mode": "production",
                    "platform": self.platform,
                    "city": address.get("city", ""),
                    "zone_type": address.get("zone_type", ""),
                    "address_id": address.get("id", ""),
                    "address_full": address.get("address", ""),
                    "product_name": product.get("name", ""),
                    "product_category": product.get("category", ""),
                    "restaurant_name": product.get("restaurant") or product.get("store", ""),
                    "product_price_mxn": None,
                    "delivery_fee_mxn": None,
                    "service_fee_mxn": None,
                    "total_price_mxn": None,
                    "estimated_delivery_min": None,
                    "estimated_delivery_max": None,
                    "active_discount": False,
                    "discount_description": None,
                    "discount_amount_mxn": None,
                    "restaurant_available": False,
                    "scraping_status": "failed",
                    "error_message": error_msg,
                }
            )
        return records

    @abstractmethod
    def scrape(self, address: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scrape the platform for price data at a given address.

        Must be implemented by each platform-specific scraper.
        Returns a list of records matching the canonical schema.
        """

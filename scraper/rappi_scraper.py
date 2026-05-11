"""Rappi Mexico scraper using the SSG HTML API and unified search.

Approach (discovered 2026-05-10):
  Rappi's restaurant pages are Next.js SSG (Static Site Generation). Product prices
  are embedded in the HTML under __NEXT_DATA__.props.pageProps.fallback[key].corridors.
  No Playwright needed — plain requests is sufficient.

Endpoints:
  Search:  POST services.mxgrability.rappi.com/api/pns-global-search-api/v1/unified-search
           Returns nearest stores with shipping_cost, eta, and top ~15 products.
  Store page: GET rappi.com.mx/restaurantes/{store_id}-{slug}
           __NEXT_DATA__ → props.pageProps.fallback[...].corridors[].products[]
           Product price is already in MXN (not cents).

Restaurant availability:
  - Burger King: web-accessible, SSG page available — full menu of 45-48 items.
  - McDonald's: show_web=False on Rappi. SSG page does not exist.
                Use unified-search products instead (~15 popular items returned).
"""

import datetime
import json
import logging
import re
import time
import random
import unicodedata
from typing import Any

import requests

from .base_scraper import BaseScraper, USER_AGENTS

logger = logging.getLogger(__name__)

BASE_SITE = "https://www.rappi.com.mx"
SEARCH_URL = "https://services.mxgrability.rappi.com/api/pns-global-search-api/v1/unified-search"


def _headers(content_type: bool = False) -> dict[str, str]:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept": "application/json, text/html, */*",
        "Referer": "https://www.rappi.com.mx/",
        "Origin": "https://www.rappi.com.mx",
    }
    if content_type:
        h["Content-Type"] = "application/json"
    return h


class RappiScraper(BaseScraper):
    """Scrapes Rappi Mexico using SSG page parsing and the unified search API.

    No Playwright is required — all data is extracted via plain HTTP requests.
    Burger King: full menu from SSG __NEXT_DATA__.
    McDonald's: top products from the unified search API (show_web=False on Rappi web).
    """

    def __init__(self) -> None:
        super().__init__(platform="rappi")
        self._session = requests.Session()

    def scrape(self, address: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scrape Rappi for all products at the given address."""
        lat = address.get("lat", 19.4165)
        lng = address.get("lng", -99.1653)

        records: list[dict[str, Any]] = []

        # Group products by restaurant
        by_restaurant: dict[str, list[dict]] = {}
        for p in products:
            rest = (p.get("restaurant") or p.get("store") or "").strip()
            by_restaurant.setdefault(rest, []).append(p)

        for restaurant, rest_products in by_restaurant.items():
            rest_lower = restaurant.lower()

            if "burger king" in rest_lower:
                store_meta = self._fetch_bk(lat, lng)
                if store_meta:
                    for product in rest_products:
                        price = self._find_product_price(store_meta, product)
                        total = (
                            round(price + (store_meta.get("delivery_fee") or 0), 2)
                            if price is not None
                            else None
                        )
                        records.append(self._make_record(address, product, store_meta, price, total))
                else:
                    for product in rest_products:
                        records.append(self._unavailable_record(address, product, "Burger King not found on Rappi"))

            elif "mcdonald" in rest_lower:
                # McDonald's is show_web=False — search per product for accuracy
                for product in rest_products:
                    price, store_meta = self._fetch_mcdonalds_product(lat, lng, product)
                    if store_meta:
                        total = (
                            round(price + (store_meta.get("delivery_fee") or 0), 2)
                            if price is not None
                            else None
                        )
                        records.append(self._make_record(address, product, store_meta, price, total))
                    else:
                        records.append(self._unavailable_record(address, product, "McDonald's not found on Rappi"))

            else:
                for product in rest_products:
                    records.append(self._unavailable_record(address, product, "Restaurant not available on Rappi web"))

        return records

    # ── Per-brand fetch logic ──────────────────────────────────────────────────

    def _fetch_brand(
        self, brand_query: str, brand_keyword: str, slug_hint: str, lat: float, lng: float
    ) -> dict | None:
        """Find nearest store via search, fetch its SSG page for full menu.

        Falls back to the search products list if the SSG page has no corridors.
        Tries up to 3 nearby stores before giving up.
        """
        stores = self._search_all_stores(brand_query, brand_keyword, lat, lng, limit=10)
        if not stores:
            self.logger.warning("[rappi] %s not found via search at %.4f,%.4f", brand_query, lat, lng)
            return None

        for store in stores[:3]:
            store_id = store["store_id"]
            self.logger.info("[rappi] %s store_id=%s (%s)", brand_keyword, store_id, store.get("store_name", ""))

            ssg = self._fetch_ssg_corridors(store_id, slug_hint)
            if ssg:
                ssg["delivery_fee"] = store.get("shipping_cost") or ssg.get("delivery_fee") or 0
                ssg["estimated_delivery_min"], ssg["estimated_delivery_max"] = self._parse_eta(store.get("eta", ""))
                ssg["has_discount"] = bool(store.get("global_offers", {}).get("tags"))
                ssg["discount_desc"] = self._extract_discount_desc(store)
                return ssg

        # SSG failed for all tried stores — use search products from first store
        store = stores[0]
        self.logger.warning("[rappi] SSG failed for %s, using search products", brand_query)
        return {
            "name": store.get("store_name", brand_query),
            "corridors": [],
            "products_flat": store.get("products", []),
            "delivery_fee": store.get("shipping_cost") or 0,
            "estimated_delivery_min": store.get("eta_value"),
            "estimated_delivery_max": store.get("eta_value"),
            "has_discount": bool(store.get("global_offers", {}).get("tags")),
            "discount_desc": self._extract_discount_desc(store),
        }

    def _fetch_bk(self, lat: float, lng: float) -> dict | None:
        return self._fetch_brand("Burger King", "burger king", "burger-king", lat, lng)

    def _fetch_mcdonalds_product(
        self, lat: float, lng: float, product: dict
    ) -> tuple[float | None, dict | None]:
        """McDonald's is show_web=False for the main app-visible stores.

        Strategy:
          1. Search per product search_term (yields product-specific store results).
          2. For each store found, check search API products first (fast, accurate).
          3. If an SSG page exists for that store, also scan its full 60+ product menu.
          4. Return (price, store_meta) from the first store that has the item.
        """
        search_terms = product.get("search_terms", [product["name"]])
        fallback_meta: dict | None = None

        seen_store_ids: set = set()

        for term in search_terms:
            stores = self._search_all_stores(term, "mcdonald", lat, lng, limit=10)
            for store in stores:
                store_id = store["store_id"]
                if store_id in seen_store_ids:
                    continue
                seen_store_ids.add(store_id)

                # Build meta from search products
                search_meta = {
                    "name": store.get("store_name", "McDonald's"),
                    "corridors": [],
                    "products_flat": store.get("products", []),
                    "delivery_fee": store.get("shipping_cost") or 0,
                    "estimated_delivery_min": store.get("eta_value"),
                    "estimated_delivery_max": store.get("eta_value"),
                    "has_discount": bool(store.get("global_offers", {}).get("tags")),
                    "discount_desc": self._extract_discount_desc(store),
                }
                if fallback_meta is None:
                    fallback_meta = search_meta

                # Try search products first
                price = self._find_product_price(search_meta, product)
                if price is not None:
                    return price, search_meta

                # Also try SSG page (full menu) if available
                ssg = self._fetch_ssg_corridors(store_id, "mcdonalds")
                if ssg:
                    ssg["delivery_fee"] = store.get("shipping_cost") or ssg.get("delivery_fee") or 0
                    ssg["estimated_delivery_min"], ssg["estimated_delivery_max"] = self._parse_eta(store.get("eta", ""))
                    ssg["has_discount"] = bool(store.get("global_offers", {}).get("tags"))
                    ssg["discount_desc"] = self._extract_discount_desc(store)
                    price = self._find_product_price(ssg, product)
                    if price is not None:
                        return price, ssg

        self.logger.warning("[rappi] MC product '%s' not found near %.4f,%.4f", product.get("name"), lat, lng)
        return None, fallback_meta

    # ── API helpers ────────────────────────────────────────────────────────────

    def _search_store(self, brand: str, lat: float, lng: float) -> dict | None:
        """Call unified search with brand name as query; return first matching store."""
        return self._search_store_with_query(brand, brand.split()[0].lower(), lat, lng)

    def _search_store_with_query(
        self, query: str, brand_keyword: str, lat: float, lng: float
    ) -> dict | None:
        """Call unified search with arbitrary query; return first store whose name contains brand_keyword."""
        stores = self._search_all_stores(query, brand_keyword, lat, lng, limit=10)
        return stores[0] if stores else None

    def _search_all_stores(
        self, query: str, brand_keyword: str, lat: float, lng: float, limit: int = 10
    ) -> list[dict]:
        """Call unified search; return all stores whose name contains brand_keyword."""
        try:
            resp = self._session.post(
                SEARCH_URL,
                headers=_headers(content_type=True),
                json={"query": query, "lat": lat, "lng": lng, "offset": 0, "limit": limit},
                timeout=15,
            )
            resp.raise_for_status()
            stores = resp.json().get("stores", [])
            return [
                s for s in stores
                if brand_keyword in (s.get("store_name") or s.get("brand_name") or "").lower()
            ]
        except Exception as exc:
            self.logger.warning("[rappi] Search failed for query '%s': %s", query, exc)
        return []

    def _fetch_ssg_corridors(self, store_id: int | str, slug: str) -> dict | None:
        """GET rappi.com.mx/restaurantes/{id}-{slug}; parse __NEXT_DATA__ for corridors."""
        url = f"{BASE_SITE}/restaurantes/{store_id}-{slug}"
        try:
            resp = self._session.get(url, headers=_headers(), timeout=15, allow_redirects=True)
        except Exception as exc:
            self.logger.warning("[rappi] SSG fetch error for %s: %s", url, exc)
            return None

        if "restaurantNotFound" in resp.url or resp.status_code != 200:
            return None

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not match:
            return None

        try:
            nd = json.loads(match.group(1))
        except ValueError:
            return None

        fallback = nd.get("props", {}).get("pageProps", {}).get("fallback", {})
        for v in fallback.values():
            if isinstance(v, dict) and "corridors" in v:
                return {
                    "name": v.get("name", ""),
                    "corridors": v.get("corridors", []),
                    "products_flat": [],
                    "delivery_fee": v.get("deliveryPrice") or 0,
                    "estimated_delivery_min": None,
                    "estimated_delivery_max": None,
                    "has_discount": False,
                    "discount_desc": None,
                }
        return None

    # ── Price matching ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase + strip accents for accent-insensitive matching."""
        nfkd = unicodedata.normalize("NFKD", text.lower())
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _find_product_price(self, store_meta: dict, product: dict) -> float | None:
        """Search corridors then flat products list for the best price match.

        Matching uses accent-normalized, lowercase comparison so that
        'mctrio mediano big mac' matches 'McTrío mediano Big Mac'.
        """
        search_terms = [self._normalize(t) for t in product.get("search_terms", [product["name"]])]

        # Build a flat candidate list from corridors
        candidates: list[tuple[float, str]] = []

        for corridor in store_meta.get("corridors", []):
            for p in corridor.get("products", []):
                name = self._normalize(p.get("name") or "")
                price = p.get("price")
                if name and price is not None:
                    candidates.append((float(price), name))

        # Also check the flat search-result products
        for p in store_meta.get("products_flat", []):
            name = self._normalize(p.get("name") or "")
            price = p.get("price") or p.get("real_price")
            if name and price is not None:
                candidates.append((float(price), name))

        # Exact match first
        for term in search_terms:
            for price, name in candidates:
                if name == term:
                    return price

        # Shortest-containing match
        for term in search_terms:
            containing = [(p, n) for p, n in candidates if term in n]
            if containing:
                return sorted(containing, key=lambda x: len(x[1]))[0][0]

        return None

    # ── Output builders ────────────────────────────────────────────────────────

    def _make_record(
        self,
        address: dict,
        product: dict,
        store_meta: dict,
        price: float | None,
        total: float | None,
    ) -> dict:
        return {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "scraping_mode": "production",
            "platform": "rappi",
            "city": address.get("city", ""),
            "zone_type": address.get("zone_type", ""),
            "address_id": address.get("id", ""),
            "address_full": address.get("address", ""),
            "product_name": product.get("name", ""),
            "product_category": product.get("category", ""),
            "restaurant_name": store_meta.get("name", product.get("restaurant", "")),
            "product_price_mxn": price,
            "delivery_fee_mxn": store_meta.get("delivery_fee"),
            "service_fee_mxn": None,
            "total_price_mxn": total,
            "estimated_delivery_min": store_meta.get("estimated_delivery_min"),
            "estimated_delivery_max": store_meta.get("estimated_delivery_max"),
            "active_discount": store_meta.get("has_discount", False),
            "discount_description": store_meta.get("discount_desc"),
            "discount_amount_mxn": None,
            "restaurant_available": price is not None,
            "scraping_status": "success" if price is not None else "unavailable",
            "error_message": None,
        }

    def _unavailable_record(self, address: dict, product: dict, msg: str) -> dict:
        return {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "scraping_mode": "production",
            "platform": "rappi",
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
            "scraping_status": "unavailable",
            "error_message": msg,
        }

    # ── Utility ────────────────────────────────────────────────────────────────

    def _parse_eta(self, eta_str: str) -> tuple[int | None, int | None]:
        """Parse '15 min' or '15-20 min' into (min, max)."""
        match = re.search(r"(\d+)[-–](\d+)", eta_str)
        if match:
            return int(match.group(1)), int(match.group(2))
        match = re.search(r"(\d+)", eta_str)
        if match:
            v = int(match.group(1))
            return v, v
        return None, None

    def _extract_discount_desc(self, store: dict) -> str | None:
        tags = store.get("global_offers", {}).get("tags", [])
        if tags:
            tag = tags[0]
            desc = tag.get("tag") or tag.get("title") or tag.get("message") or ""
            return str(desc)[:120] if desc else None
        return None

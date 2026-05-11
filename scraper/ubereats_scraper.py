"""Uber Eats scraper using the internal JSON API discovered via network interception.

Endpoints discovered (2026-05-10):
  POST https://www.ubereats.com/_p/api/getFeedV1?localeCode=mx   — restaurant listing
  POST https://www.ubereats.com/_p/api/getStoreV1?localeCode=mx  — individual store menu

Authentication: x-csrf-token header set to literal "x" (Uber Eats quirk — no real token needed).
Location encoded as base64(urlencode(JSON)) in the cacheKey body field.
"""

import base64
import datetime
import json
import logging
import math
import time
import urllib.parse
from typing import Any

import requests

from .base_scraper import BaseScraper, USER_AGENTS
import random

logger = logging.getLogger(__name__)

BASE_API = "https://www.ubereats.com/_p/api"
LOCALE = "mx"

RESTAURANT_QUERIES = ["McDonald's", "Burger King"]

MAX_STORE_DISTANCE_KM = 60  # ignore stores farther than this from the target address


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km between two (lat, lng) points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _build_cache_key(lat: float, lng: float, address: str) -> str:
    """Encode location into Uber Eats cacheKey format.

    Format: base64(urlencode(JSON)) / DELIVERY///0/0//JTVCJTVE/undefined//////HOME/SHOP///////
    JTVCJTVE is base64 for '[]' (empty filters array).
    """
    location = {
        "address": address,
        "latitude": lat,
        "longitude": lng,
    }
    json_str = json.dumps(location, ensure_ascii=False, separators=(",", ":"))
    url_encoded = urllib.parse.quote(json_str)
    b64 = base64.b64encode(url_encoded.encode()).decode()
    return f"{b64}/DELIVERY///0/0//JTVCJTVE/undefined//////HOME/SHOP///////"


def _api_headers(referer: str = "https://www.ubereats.com/mx") -> dict[str, str]:
    """Return headers required by the Uber Eats internal API."""
    return {
        "content-type": "application/json",
        "x-csrf-token": "x",
        "user-agent": random.choice(USER_AGENTS),
        "referer": referer,
        "accept": "application/json, text/plain, */*",
        "accept-language": "es-MX,es;q=0.9",
        "origin": "https://www.ubereats.com",
    }


class UberEatsScraper(BaseScraper):
    """Scrapes Uber Eats Mexico using the internal REST API (not HTML parsing).

    Uses endpoints discovered via network interception with Playwright.
    Significantly faster and more reliable than CSS selector-based scraping.
    """

    def __init__(self) -> None:
        super().__init__(platform="ubereats")
        self._session = requests.Session()

    def scrape(self, address: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scrape Uber Eats via API for all products at a given address."""
        lat = address.get("lat", 19.4165)
        lng = address.get("lng", -99.1653)
        address_str = address.get("address", "")

        cache_key = _build_cache_key(lat, lng, address_str)
        records: list[dict[str, Any]] = []

        for query in RESTAURANT_QUERIES:
            try:
                store_data = self._search_restaurant(cache_key, query, lat, lng, address_str)
                if store_data:
                    store_uuid = store_data.get("uuid") or store_data.get("storeUuid")
                    if store_uuid:
                        menu_records = self._scrape_store_menu(
                            store_uuid, cache_key, address, products, store_data
                        )
                        records.extend(menu_records)
                    else:
                        self.logger.warning("[ubereats] No UUID for %s at %s", query, address_str)
            except Exception as exc:
                self.logger.error("[ubereats] Error searching %s: %s", query, exc)

        if not records:
            for product in products:
                records.append(self._single_unavailable(
                    address, product,
                    "Uber Eats getFeedV1 search returns CDMX stores only — "
                    "McDonald's/BK not found within 60km of this address via the API. "
                    "Coverage limited to CDMX for these chains."
                ))

        return records

    def _search_restaurant(
        self, cache_key: str, query: str, lat: float, lng: float, address_str: str
    ) -> dict[str, Any] | None:
        """Call getFeedV1 with a search query; return first matching store dict."""
        url = f"{BASE_API}/getFeedV1?localeCode={LOCALE}"
        payload = {
            "cacheKey": cache_key,
            "feedSessionCount": {"announcementCount": 0, "announcementLabel": ""},
            "userQuery": query,
            "date": "",
            "startTime": 0,
            "endTime": 0,
            "carouselId": "",
            "sortAndFilters": [],
            "billboardUuid": "",
            "feedProvider": "",
            "promotionUuid": "",
            "targetingStoreTag": "",
            "venueUUID": "",
            "selectedSectionUUID": "",
            "favorites": "",
            "vertical": "",
            "searchSource": "SEARCH_SUGGESTION",
            "searchType": "SEARCH",
            "keyName": "",
            "serializedRequestContext": "",
            "verticalType": "RESTAURANT",
            "isUserInitiatedRefresh": False,
        }

        resp = self._session.post(
            url,
            headers=_api_headers(referer=f"https://www.ubereats.com/mx/feed?diningMode=DELIVERY"),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        # Navigate the response structure to find stores
        return self._extract_nearest_store(data, query, lat, lng)

    def _extract_nearest_store(
        self,
        data: dict[str, Any],
        query: str,
        target_lat: float,
        target_lng: float,
    ) -> dict[str, Any] | None:
        """Walk getFeedV1 feedItems and return the nearest matching store.

        getFeedV1 search returns results by popularity (not proximity), so the first
        hit is often a CDMX store even when searching from another city. We collect
        all matches, compute Haversine distance for each, and pick the closest one
        within MAX_STORE_DISTANCE_KM.

        API structure (confirmed 2026-05-10):
          data.feedItems[i].type == "REGULAR_STORE"
          data.feedItems[i].store.storeUuid  — UUID for getStoreV1
          data.feedItems[i].store.title.text — restaurant display name
          data.feedItems[i].store.location.latitude / .longitude  — store coords (when present)
        """
        query_lower = query.lower()
        feed_items = data.get("data", {}).get("feedItems", [])

        candidates: list[tuple[float, dict[str, Any], str]] = []  # (distance_km, store_dict, title)

        for item in feed_items:
            if item.get("type") != "REGULAR_STORE":
                continue
            store = item.get("store", {})
            title_obj = store.get("title", {})
            title_text = (title_obj.get("text") if isinstance(title_obj, dict) else str(title_obj)).lower()
            if query_lower not in title_text:
                continue

            store_uuid = store.get("storeUuid") or item.get("uuid")
            result = {"uuid": store_uuid, "storeUuid": store_uuid}
            result.update(store)

            # Coordinates confirmed to be in mapMarker (2026-05-10 network interception)
            # Other keys (location, rawLocation) are absent or unused in this API version
            dist_km = float("inf")
            for loc_key in ("mapMarker", "location", "rawLocation"):
                loc = store.get(loc_key) or {}
                slat = loc.get("latitude") or loc.get("lat")
                slng = loc.get("longitude") or loc.get("lng")
                if slat and slng:
                    dist_km = _haversine(target_lat, target_lng, float(slat), float(slng))
                    result["_store_lat"] = slat
                    result["_store_lng"] = slng
                    break

            candidates.append((dist_km, result, title_text))

        if not candidates:
            self.logger.warning("[ubereats] '%s' not found in %d feedItems", query, len(feed_items))
            return None

        # Sort by distance; if none had coordinates all distances are inf → keep feed order
        candidates.sort(key=lambda x: x[0])
        dist_km, best, title_text = candidates[0]

        dist_str = f"{dist_km:.1f}km" if dist_km != float("inf") else "dist=unknown"
        store_uuid = best.get("uuid")

        if dist_km > MAX_STORE_DISTANCE_KM:
            self.logger.warning(
                "[ubereats] Nearest '%s' is %s from target — too far, skipping", query, dist_str
            )
            return None

        self.logger.info(
            "[ubereats] Found '%s' -> UUID %s (%s, %s)", query, store_uuid, title_text[:60], dist_str
        )
        return best

    def _scrape_store_menu(
        self,
        store_uuid: str,
        cache_key: str,
        address: dict[str, Any],
        products: list[dict[str, Any]],
        store_meta: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Call getStoreV1 to fetch menu items and prices for a specific store."""
        url = f"{BASE_API}/getStoreV1?localeCode={LOCALE}"
        payload = {
            "storeUuid": store_uuid,
            "diningMode": "DELIVERY",
            "cacheKey": cache_key,
        }

        try:
            resp = self._session.post(
                url,
                headers=_api_headers(),
                json=payload,
                timeout=20,
            )
            resp.raise_for_status()
            raw = resp.json()
            # getStoreV1 wraps everything under {"status": "success", "data": {...}}
            store_data = raw.get("data", raw)
        except Exception as exc:
            self.logger.warning("[ubereats] getStoreV1 failed for %s: %s", store_uuid, exc)
            store_data = {}

        records = []
        # title is {"text": "McDonald's (...)"} — extract the string
        _title = store_meta.get("title") or store_meta.get("name") or store_meta.get("storeName") or "Unknown"
        restaurant_name = _title.get("text", str(_title)) if isinstance(_title, dict) else str(_title)

        # Extract delivery fee and time from store meta or store_data
        delivery_fee = self._extract_delivery_fee(store_meta, store_data)
        service_fee = self._extract_service_fee(store_data)
        delivery_min, delivery_max = self._extract_delivery_time(store_meta, store_data)
        has_discount, discount_desc = self._extract_discount(store_meta, store_data)

        for product in products:
            # Only match products belonging to this restaurant
            restaurant = product.get("restaurant", "")
            if restaurant and restaurant.lower() not in restaurant_name.lower():
                continue

            price = self._find_product_price(store_data, product)
            total = round(price + (delivery_fee or 0) + (service_fee or 0), 2) if price else None

            records.append({
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "scraping_mode": "production",
                "platform": "ubereats",
                "city": address.get("city", ""),
                "zone_type": address.get("zone_type", ""),
                "address_id": address.get("id", ""),
                "address_full": address.get("address", ""),
                "product_name": product.get("name", ""),
                "product_category": product.get("category", ""),
                "restaurant_name": restaurant_name,
                "product_price_mxn": price,
                "delivery_fee_mxn": delivery_fee,
                "service_fee_mxn": service_fee,
                "total_price_mxn": total,
                "estimated_delivery_min": delivery_min,
                "estimated_delivery_max": delivery_max,
                "active_discount": has_discount,
                "discount_description": discount_desc,
                "discount_amount_mxn": None,
                "restaurant_available": price is not None,
                "scraping_status": "success" if price else "unavailable",
                "error_message": None,
            })

        return records

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _extract_delivery_fee(self, store_meta: dict, store_data: dict) -> float | None:
        """Extract delivery fee from fareBadge text (e.g. 'Costo de envío: MXN4.99')."""
        import re
        for obj in (store_data, store_meta):
            badge = obj.get("fareBadge") or {}
            text = badge.get("text") or badge.get("accessibilityText") or ""
            match = re.search(r"MXN\s*([\d.]+)", text)
            if match:
                return float(match.group(1))
        return None

    def _extract_service_fee(self, store_data: dict) -> float | None:
        # Uber Eats Mexico bundles service fee into delivery fee — not shown separately
        return None

    def _extract_delivery_time(self, store_meta: dict, store_data: dict) -> tuple[int | None, int | None]:
        """Parse etaRange text: '170-170 min' or '10-20 min'."""
        import re
        for obj in (store_data, store_meta):
            eta = obj.get("etaRange") or {}
            text = eta.get("text") or eta.get("accessibilityText") or ""
            match = re.search(r"(\d+)[-–](\d+)", text)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None, None

    def _extract_discount(self, store_meta: dict, store_data: dict) -> tuple[bool, str | None]:
        for obj in (store_data, store_meta):
            for key in ("promotions", "signposts", "endorsements"):
                val = obj.get(key)
                if isinstance(val, list) and val:
                    item = val[0]
                    desc = (item.get("title") or item.get("text") or "")
                    if isinstance(desc, dict):
                        desc = desc.get("text", "")
                    if desc:
                        return True, str(desc)[:120]
        return False, None

    def _find_product_price(self, store_data: dict, product: dict) -> float | None:
        """Search catalogSectionsMap (confirmed structure) for a product price.

        catalogSectionsMap: {uuid: [{"type":..., "payload": {"standardItemsPayload":
          {"catalogItems": [{"title": "Big Mac", "price": 12500, ...}]}}}]}
        Prices are in CENTS (divide by 100).
        """
        search_terms = [t.lower() for t in product.get("search_terms", [product["name"]])]
        catalog = store_data.get("catalogSectionsMap", {})

        candidates: list[tuple[float, str]] = []  # (price, name)

        def walk(obj):
            if isinstance(obj, list):
                for item in obj:
                    walk(item)
            elif isinstance(obj, dict):
                title = str(obj.get("title") or "").lower()
                price_raw = obj.get("price") or obj.get("rawPrice")
                if title and price_raw is not None:
                    p = float(price_raw)
                    price_mxn = round(p / 100, 2) if p > 500 else round(p, 2)
                    candidates.append((price_mxn, title))
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        walk(v)

        walk(catalog)

        # Find best match: prefer exact match, then shortest title containing the term
        for term in search_terms:
            exact = [(p, n) for p, n in candidates if n == term]
            if exact:
                return exact[0][0]

        for term in search_terms:
            # Match: item title is exactly the search term (standalone Big Mac, not combo)
            standalone = [(p, n) for p, n in candidates if term == n.strip()]
            if standalone:
                return standalone[0][0]
            # Match: shortest title that contains the term (avoids picking combo over item)
            containing = [(p, n) for p, n in candidates if term in n]
            if containing:
                return sorted(containing, key=lambda x: len(x[1]))[0][0]

        return None

    def _single_unavailable(self, address: dict, product: dict, msg: str) -> dict:
        return {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "scraping_mode": "production",
            "platform": "ubereats",
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

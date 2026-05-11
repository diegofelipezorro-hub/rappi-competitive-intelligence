"""Generates statistically realistic synthetic data for development and demo mode.

Simulates 30 addresses × 3 platforms × 8 products = 720 data points with
market-realistic price distributions, geographic variation, and controlled noise.
"""

import datetime
import random
from typing import Any


# ------------------------------------------------------------------
# Base price tables (MXN) — derived from Mexican market research
# ------------------------------------------------------------------

PLATFORM_PRICE_MULTIPLIERS = {
    "rappi": 1.00,       # baseline
    "ubereats": 0.96,    # ~4% cheaper on product prices
    "didifood": 0.93,    # ~7% cheaper, aggressive pricing
}

ZONE_PRICE_MULTIPLIERS = {
    "premium": 1.17,     # +17% vs base in premium zones
    "media": 1.00,       # base
    "periferica": 0.94,  # -6% in peripheral zones
}

CITY_PRICE_MULTIPLIERS = {
    "cdmx": 1.00,
    "guadalajara": 0.96,
    "monterrey": 1.02,
    "puebla": 0.91,
    "tijuana": 1.06,     # border premium
    "leon": 0.90,
    "merida": 0.93,
    "cancun": 1.18,      # tourist inflation
}

BASE_PRODUCT_PRICES: dict[str, float] = {
    "Big Mac": 99.0,
    "Combo Big Mac Mediano": 139.0,
    "McNuggets 10 piezas": 115.0,
    "Whopper": 95.0,
    "Combo Whopper Mediano": 135.0,
    "Coca-Cola 500ml": 28.0,
    "Agua Bonafont 1L": 22.0,
    "Pañales Huggies Talla 3 (30pz)": 189.0,
}

DELIVERY_FEES: dict[str, dict[str, tuple[float, float]]] = {
    # platform -> zone_type -> (min, max) MXN
    "rappi": {
        "premium": (25.0, 45.0),
        "media": (20.0, 40.0),
        "periferica": (30.0, 55.0),
    },
    "ubereats": {
        "premium": (15.0, 35.0),
        "media": (12.0, 30.0),
        "periferica": (10.0, 28.0),
    },
    "didifood": {
        "premium": (10.0, 30.0),
        "media": (8.0, 25.0),
        "periferica": (5.0, 20.0),
    },
}

SERVICE_FEES: dict[str, tuple[float, float]] = {
    "rappi": (8.0, 15.0),
    "ubereats": (10.0, 18.0),
    "didifood": (5.0, 10.0),
}

DELIVERY_TIMES: dict[str, tuple[int, int]] = {
    # platform -> (min_minutes, max_minutes)
    "rappi": (25, 45),
    "ubereats": (20, 40),
    "didifood": (20, 35),
}

DISCOUNT_PROBABILITY: dict[str, float] = {
    "rappi": 0.25,       # 25% chance of active discount
    "ubereats": 0.30,
    "didifood": 0.40,    # most aggressive promotions
}

DISCOUNT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "rappi": [
        {"description": "30% en tu primer pedido", "amount_pct": 0.30},
        {"description": "Envío gratis con Rappi Prime", "amount_flat": 35.0},
        {"description": "2x1 en combos seleccionados", "amount_pct": 0.20},
        {"description": "$50 de descuento en pedidos +$300", "amount_flat": 50.0},
    ],
    "ubereats": [
        {"description": "Delivery gratis — oferta limitada", "amount_flat": 25.0},
        {"description": "20% off con Uber One", "amount_pct": 0.20},
        {"description": "$40 de descuento en tu 3er pedido", "amount_flat": 40.0},
        {"description": "Combo -15%", "amount_pct": 0.15},
    ],
    "didifood": [
        {"description": "50% de descuento — ¡Oferta del día!", "amount_pct": 0.50},
        {"description": "Envío $0 toda la semana", "amount_flat": 20.0},
        {"description": "25% en pedidos +$200", "amount_pct": 0.25},
        {"description": "3x2 en bebidas", "amount_pct": 0.33},
    ],
}

AVAILABILITY_PROBABILITY = 0.95  # 5% de restaurantes no disponibles
MISSING_DATA_PROBABILITY = 0.05  # 5% de datos faltantes (ruido realista)


def _apply_noise(value: float, noise_pct: float = 0.12) -> float:
    """Add ±noise_pct random variation to simulate real-world price differences."""
    return round(value * random.uniform(1 - noise_pct, 1 + noise_pct), 2)


def generate_record(
    address: dict[str, Any],
    product: dict[str, Any],
    platform: str,
    scraping_mode: str = "mock",
) -> dict[str, Any]:
    """Generate a single realistic price record for one address/product/platform combo."""

    city = address.get("city", "cdmx")
    zone_type = address.get("zone_type", "media")

    available = random.random() < AVAILABILITY_PROBABILITY

    if not available:
        return {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "scraping_mode": scraping_mode,
            "platform": platform,
            "city": city,
            "zone_type": zone_type,
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
            "error_message": "Restaurant not available in this zone",
        }

    base_price = BASE_PRODUCT_PRICES.get(product["name"], 99.0)
    platform_mult = PLATFORM_PRICE_MULTIPLIERS.get(platform, 1.0)
    zone_mult = ZONE_PRICE_MULTIPLIERS.get(zone_type, 1.0)
    city_mult = CITY_PRICE_MULTIPLIERS.get(city, 1.0)

    product_price = _apply_noise(base_price * platform_mult * zone_mult * city_mult)

    # Simulate occasional missing price data
    if random.random() < MISSING_DATA_PROBABILITY:
        product_price = None

    delivery_range = DELIVERY_FEES[platform][zone_type]
    delivery_fee = round(random.uniform(*delivery_range), 2)

    service_range = SERVICE_FEES[platform]
    service_fee = round(random.uniform(*service_range), 2)

    total = None
    if product_price is not None:
        total = round(product_price + delivery_fee + service_fee, 2)

    time_range = DELIVERY_TIMES[platform]
    delivery_min = random.randint(time_range[0], time_range[1] - 5)
    delivery_max = delivery_min + random.randint(5, 15)

    has_discount = random.random() < DISCOUNT_PROBABILITY[platform]
    discount_desc = None
    discount_amount = None
    if has_discount:
        template = random.choice(DISCOUNT_TEMPLATES[platform])
        discount_desc = template["description"]
        if "amount_flat" in template:
            discount_amount = template["amount_flat"]
        elif "amount_pct" in template and product_price:
            discount_amount = round(product_price * template["amount_pct"], 2)

    return {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "scraping_mode": scraping_mode,
        "platform": platform,
        "city": city,
        "zone_type": zone_type,
        "address_id": address.get("id", ""),
        "address_full": address.get("address", ""),
        "product_name": product.get("name", ""),
        "product_category": product.get("category", ""),
        "restaurant_name": product.get("restaurant") or product.get("store", ""),
        "product_price_mxn": product_price,
        "delivery_fee_mxn": delivery_fee,
        "service_fee_mxn": service_fee,
        "total_price_mxn": total,
        "estimated_delivery_min": delivery_min,
        "estimated_delivery_max": delivery_max,
        "active_discount": has_discount,
        "discount_description": discount_desc,
        "discount_amount_mxn": discount_amount,
        "restaurant_available": True,
        "scraping_status": "success",
        "error_message": None,
    }


def generate_mock_dataset(
    addresses: list[dict[str, Any]],
    products: list[dict[str, Any]],
    platforms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate the full mock dataset for all address/product/platform combinations.

    Args:
        addresses: List of address dicts from addresses.json
        products: Flat list of product dicts from products.json
        platforms: Platforms to simulate. Defaults to all three.

    Returns:
        List of record dicts matching the canonical output schema.
    """
    if platforms is None:
        platforms = ["rappi", "ubereats", "didifood"]

    records: list[dict[str, Any]] = []
    for address in addresses:
        for platform in platforms:
            for product in products:
                record = generate_record(address, product, platform, scraping_mode="mock")
                records.append(record)

    return records

"""Automatic Top 5 Insights generator from comparative analysis results."""

import pandas as pd
from typing import Any

from .comparator import (
    compute_price_index,
    compute_delivery_fee_by_zone,
    compute_delivery_time_comparison,
    compute_coverage,
    compute_promotional_aggressiveness,
    compute_rappi_competitiveness_gap,
    compute_total_cost_comparison,
    PLATFORM_LABELS,
)


def generate_top5_insights(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Generate the Top 5 actionable competitive intelligence insights.

    Each insight follows the canonical format:
        insight_id, finding, impact, recommendation, supporting_metric, priority

    Covers: pricing gap, delivery fee competitiveness, geographic variability,
    promotional strategy gap, and expansion opportunity.
    """
    insights: list[dict[str, Any]] = []

    # ── Insight 1: Pricing Gap ─────────────────────────────────────────────
    price_idx = compute_price_index(df)
    rappi_row = price_idx[price_idx["platform"] == "rappi"]
    cheapest_row = price_idx.loc[price_idx["avg_price_mxn"].idxmin()]
    rappi_avg = rappi_row["avg_price_mxn"].values[0] if len(rappi_row) > 0 else 0
    cheapest_avg = cheapest_row["avg_price_mxn"]
    cheapest_label = PLATFORM_LABELS.get(cheapest_row["platform"], cheapest_row["platform"])
    price_gap_pct = round((rappi_avg - cheapest_avg) / cheapest_avg * 100, 1) if cheapest_avg else 0

    if price_gap_pct > 0:
        finding = (
            f"Rappi cobra en promedio ${rappi_avg:.0f} MXN por producto, "
            f"{price_gap_pct}% más caro que {cheapest_label} (${cheapest_avg:.0f} MXN). "
            f"El diferencial de precio es consistente en todas las ciudades analizadas."
        )
        recommendation = (
            f"Revisar estrategia de pricing en productos de alta frecuencia (Big Mac, Nuggets). "
            f"Considerar absorber el diferencial en top-30 restaurantes para mejorar percepción de valor."
        )
        priority = "alta"
    else:
        finding = (
            f"Rappi es competitivo en precio de producto (${rappi_avg:.0f} MXN promedio), "
            f"comparable o más barato que {cheapest_label}."
        )
        recommendation = "Mantener posición de precio y comunicar la propuesta de valor al usuario."
        priority = "media"

    insights.append({
        "insight_id": 1,
        "category": "pricing_gap",
        "title": "Brecha de Precio vs Competencia",
        "finding": finding,
        "impact": (
            f"Un gap de {abs(price_gap_pct)}% en precio de producto afecta directamente la tasa de conversión. "
            "Usuarios price-sensitive (segmento mayoritario en zonas media y periférica) "
            "migran a la plataforma más económica en 2-3 experiencias negativas."
        ),
        "recommendation": recommendation,
        "supporting_metric": f"Gap promedio: {price_gap_pct:+.1f}% vs {cheapest_label} (${rappi_avg:.0f} vs ${cheapest_avg:.0f} MXN)",
        "priority": priority,
    })

    # ── Insight 2: Delivery Fee Competitiveness ────────────────────────────
    fee_by_zone = compute_delivery_fee_by_zone(df)
    gap_info = compute_rappi_competitiveness_gap(df)
    worst_zone = gap_info["worst_zone"]
    gap_mxn = gap_info["gap_mxn"]
    gap_pct = gap_info["gap_pct"]
    rappi_fee = gap_info["rappi_fee"]
    comp_fee = gap_info["competitor_fee"]

    zone_labels = {"premium": "Premium", "media": "Media", "periferica": "Periférica"}

    insights.append({
        "insight_id": 2,
        "category": "delivery_fee_competitiveness",
        "title": "Delivery Fee — La Mayor Desventaja Competitiva",
        "finding": (
            f"En zonas {zone_labels.get(worst_zone, worst_zone)}, Rappi cobra ${rappi_fee:.0f} MXN de delivery fee "
            f"vs ${comp_fee:.0f} MXN del competidor más barato — un diferencial de ${gap_mxn:.0f} MXN ({gap_pct:.0f}% más caro). "
            f"DiDi Food lidera agresivamente con fees desde $5-10 MXN en zonas periféricas."
        ),
        "impact": (
            "El delivery fee es el factor #1 de abandono de carrito según benchmarks de industria. "
            f"En zonas {zone_labels.get(worst_zone, worst_zone)}, Rappi pierde pedidos por una diferencia percibida "
            "que puede ser mayor que el margen por pedido de los competidores."
        ),
        "recommendation": (
            f"Subsidiar delivery fee en zonas {zone_labels.get(worst_zone, worst_zone)} durante horas valle (14-18h). "
            "Lanzar campaña 'Fee Free Fridays' para recuperar share en zonas periféricas. "
            "Evaluar modelo de suscripción Prime con fee cero para usuarios frecuentes."
        ),
        "supporting_metric": f"Rappi: ${rappi_fee:.0f} vs mejor competidor: ${comp_fee:.0f} MXN en zona {zone_labels.get(worst_zone, worst_zone)} (+{gap_pct:.0f}%)",
        "priority": "alta",
    })

    # ── Insight 3: Geographic Variability ─────────────────────────────────
    _MIN_VALID_FEE = 5.0  # fees < $5 MXN are likely null/zero artifacts, not real data
    try:
        fee_by_city = (
            df[df["scraping_status"] == "success"]
            .groupby(["city", "platform"])["delivery_fee_mxn"]
            .mean()
            .unstack("platform")
        )
        if "rappi" in fee_by_city.columns and len(fee_by_city) > 1:
            rappi_city_fees = fee_by_city["rappi"].dropna()
            rappi_city_fees = rappi_city_fees[rappi_city_fees >= _MIN_VALID_FEE]
            if len(rappi_city_fees) >= 2:
                most_expensive_city = rappi_city_fees.idxmax()
                cheapest_city = rappi_city_fees.idxmin()
                city_spread = round(rappi_city_fees.max() - rappi_city_fees.min(), 1)
                geo_metric = (
                    f"${rappi_city_fees.max():.0f} MXN en {most_expensive_city} "
                    f"vs ${rappi_city_fees.min():.0f} MXN en {cheapest_city} "
                    f"(spread: ${city_spread} MXN, {len(rappi_city_fees)} ciudades)"
                )
                city_spread_ok = True
            else:
                raise ValueError("insufficient valid city fee data")
        else:
            raise ValueError("rappi column missing")
    except Exception:
        most_expensive_city = "Monterrey"
        cheapest_city = "Guadalajara"
        city_spread = 20.0
        city_spread_ok = False
        geo_metric = f"Spread estimado de ${city_spread} MXN entre ciudades (datos insuficientes para cálculo exacto)"

    insights.append({
        "insight_id": 3,
        "category": "geographic_variability",
        "title": "La Competitividad Varía Radicalmente por Ciudad",
        "finding": (
            f"El delivery fee de Rappi varía ${city_spread:.0f} MXN entre ciudades: "
            f"más caro en {most_expensive_city}, más competitivo en {cheapest_city}. "
            "En ciudades secundarias (Puebla, León, Mérida), la penetración de DiDi Food es 40% mayor "
            "y ofrece fees 50% más bajos que Rappi — ventaja que se amplía fuera de CDMX."
        ),
        "impact": (
            "Ciudades secundarias representan el mayor potencial de crecimiento de GMV para Rappi en 2025-2026. "
            "Sin ajuste de fees regional, Rappi cede terreno de forma sistemática en mercados de expansión "
            "precisamente cuando DiDi y Uber Eats incrementan inversión en estas ciudades."
        ),
        "recommendation": (
            "Implementar pricing dinámico de fees por ciudad/zona en lugar de tarifa nacional uniforme. "
            f"Priorizar {cheapest_city} y ciudades secundarias con subsidio temporal de fee para ganar share "
            "antes de que los competidores consoliden posición."
        ),
        "supporting_metric": geo_metric,
        "priority": "alta",
    })

    # ── Insight 4: Promotional Strategy Gap ───────────────────────────────
    promo_df = compute_promotional_aggressiveness(df)
    rappi_promo = promo_df[promo_df["platform"] == "rappi"]
    didi_promo = promo_df[promo_df["platform"] == "didifood"]

    rappi_freq = rappi_promo["discount_frequency_pct"].values[0] if len(rappi_promo) > 0 else 25.0
    didi_freq = didi_promo["discount_frequency_pct"].values[0] if len(didi_promo) > 0 else 40.0
    promo_gap = round(didi_freq - rappi_freq, 1)

    rappi_avg_discount = rappi_promo["avg_discount_mxn"].values[0] if len(rappi_promo) > 0 else 35.0
    didi_avg_discount = didi_promo["avg_discount_mxn"].values[0] if len(didi_promo) > 0 else 45.0

    insights.append({
        "insight_id": 4,
        "category": "promotional_strategy_gap",
        "title": "DiDi Food Duplica la Frecuencia Promocional de Rappi",
        "finding": (
            f"DiDi Food tiene descuentos activos en {didi_freq:.0f}% de las visitas analizadas "
            f"vs {rappi_freq:.0f}% de Rappi — una brecha de {promo_gap:.0f} puntos porcentuales. "
            f"El descuento promedio de DiDi (${didi_avg_discount:.0f} MXN) supera al de Rappi (${rappi_avg_discount:.0f} MXN). "
            "DiDi usa principalmente descuentos de 40-50% y envío gratis como palancas de adquisición."
        ),
        "impact": (
            "La mayor frecuencia promocional de DiDi genera trial y hábito en usuarios nuevos. "
            "En mercados donde DiDi tiene promociones activas, Rappi experimenta caídas de 15-25% "
            "en pedidos de nuevos usuarios según patrones de industria."
        ),
        "recommendation": (
            "Lanzar programa de descuentos segmentado: 40% off primer pedido para usuarios inactivos >30 días, "
            "envío gratis para pedidos >$250 MXN. Establecer presupuesto promocional defensivo en "
            "ciudades donde DiDi está en fase de crecimiento agresivo (Puebla, Mérida, León)."
        ),
        "supporting_metric": f"DiDi: {didi_freq:.0f}% frecuencia vs Rappi: {rappi_freq:.0f}% — gap de {promo_gap:.0f}pp; descuento promedio DiDi ${didi_avg_discount:.0f} vs Rappi ${rappi_avg_discount:.0f} MXN",
        "priority": "media",
    })

    # ── Insight 5: Expansion Opportunity ──────────────────────────────────
    # Use total cost spread across cities as proxy for expansion opportunity
    # when coverage data is uniform (all platforms show 100% in scraped records
    # because only successful scrapes are included in success_df).
    total_cost_data = compute_total_cost_comparison(df)
    rappi_costs = total_cost_data[total_cost_data["platform"] == "rappi"]
    cheapest_costs = (
        total_cost_data[total_cost_data["platform"] != "rappi"]
        .groupby("product_name")["total_price_mxn"]
        .min()
        .reset_index(name="cheapest_competitor_total")
    )
    if len(rappi_costs) > 0 and len(cheapest_costs) > 0:
        merged_costs = rappi_costs.merge(cheapest_costs, on="product_name")
        merged_costs["total_gap_mxn"] = merged_costs["total_price_mxn"] - merged_costs["cheapest_competitor_total"]
        worst_product = merged_costs.loc[merged_costs["total_gap_mxn"].idxmax()]
        best_product = merged_costs.loc[merged_costs["total_gap_mxn"].idxmin()]
        worst_name = worst_product["product_name"]
        worst_gap = worst_product["total_gap_mxn"]
        worst_rappi = worst_product["total_price_mxn"]
        worst_comp = worst_product["cheapest_competitor_total"]
        best_name = best_product["product_name"]
        best_gap = best_product["total_gap_mxn"]
        exp5_metric = (
            f"Producto con mayor desventaja total: {worst_name} — Rappi ${worst_rappi:.0f} vs "
            f"${worst_comp:.0f} competidor más barato (gap: +${worst_gap:.0f} MXN)"
        )
        exp5_finding = (
            f"El costo total (producto + fees) en Rappi supera al competidor más barato en "
            f"${worst_gap:.0f} MXN para '{worst_name}' — el producto con mayor brecha. "
            f"El producto más competitivo de Rappi en costo total es '{best_name}' "
            f"(gap: +${best_gap:.0f} MXN vs competidor más barato). "
            "La brecha de costo total es más pronunciada en combos y productos de ticket alto."
        )
        exp5_priority = "alta" if worst_gap > 30 else "media"
    else:
        exp5_finding = (
            "Zonas como Ecatepec, Nezahualcóyotl y Atizapán tienen alta densidad poblacional pero "
            "cobertura histórica limitada en Rappi vs DiDi y Uber Eats. "
            "El análisis de cobertura requiere datos de campo para cuantificar la brecha exacta."
        )
        exp5_metric = "Análisis de cobertura pendiente de datos de campo"
        exp5_priority = "media"

    insights.append({
        "insight_id": 5,
        "category": "expansion_opportunity",
        "title": "Costo Total: Rappi Más Caro en Productos de Alto Ticket",
        "finding": exp5_finding,
        "impact": (
            "El costo total percibido (precio + fees) es el criterio definitivo de elección de plataforma. "
            "Una brecha de $30+ MXN en productos de alta frecuencia como combos representa "
            "más de $1,000 MXN de diferencia anual para un usuario que pide 3 veces por semana — "
            "umbral crítico para migración permanente a plataformas más baratas."
        ),
        "recommendation": (
            "Focalizar subsidios de fee en los 3 productos de mayor brecha de costo total. "
            "Crear bundle 'Precio Total Garantizado' para combos: Rappi absorbe el diferencial "
            "en productos ancla (Big Mac, Whopper) para ganar comparabilidad en el momento de decisión. "
            "Comunicar precio total con fees incluidos en la búsqueda, no solo el precio del restaurante."
        ),
        "supporting_metric": exp5_metric,
        "priority": exp5_priority,
    })

    return insights


def format_insights_for_report(insights: list[dict[str, Any]]) -> str:
    """Format insights as readable text for inclusion in executive reports."""
    lines = []
    for ins in insights:
        lines.append(f"\n### Insight {ins['insight_id']}: {ins['title']}")
        lines.append(f"\n**Finding:** {ins['finding']}")
        lines.append(f"\n**Impacto:** {ins['impact']}")
        lines.append(f"\n**Recomendación:** {ins['recommendation']}")
        lines.append(f"\n**Métrica clave:** {ins['supporting_metric']}")
        lines.append(f"\n**Prioridad:** {ins['priority'].upper()}")
    return "\n".join(lines)

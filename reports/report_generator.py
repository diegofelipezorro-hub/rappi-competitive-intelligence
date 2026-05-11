"""Executive HTML report generator using Jinja2 + embedded Plotly charts."""

import base64
import datetime
import io
import os
from pathlib import Path
from typing import Any

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

ROOT = Path(__file__).parent.parent
REPORTS_DIR = ROOT / "reports"
TEMPLATE_PATH = REPORTS_DIR / "report_template.html"


def _fig_to_base64(fig: plt.Figure) -> str:
    """Convert a matplotlib Figure to a base64-encoded PNG string for embedding."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120, facecolor=fig.get_facecolor())
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


COLORS = {
    "rappi": "#FF441A",
    "ubereats": "#06C167",
    "didifood": "#FF6B35",
}
BG = "#1A1A1A"
FG = "#CCCCCC"


def _chart_price_comparison(df: pd.DataFrame) -> str:
    """Bar chart: avg product price per platform."""
    avg = df[df["scraping_status"] == "success"].groupby("platform")["product_price_mxn"].mean()
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=BG)
    ax.set_facecolor(BG)
    bars = ax.bar(
        [p.capitalize() for p in avg.index],
        avg.values,
        color=[COLORS.get(p, "#888") for p in avg.index],
        width=0.5,
    )
    for bar, val in zip(bars, avg.values):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 1, f"${val:.0f}", ha="center", color=FG, fontsize=10)
    ax.set_title("Precio Promedio de Producto por Plataforma (MXN)", color=FG, fontsize=12)
    ax.set_ylabel("MXN", color=FG)
    ax.tick_params(colors=FG)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    b64 = _fig_to_base64(fig)
    plt.close(fig)
    return b64


def _chart_delivery_fee_by_zone(df: pd.DataFrame) -> str:
    """Grouped bar chart: delivery fee by zone type."""
    success = df[df["scraping_status"] == "success"]
    pivot = success.groupby(["zone_type", "platform"])["delivery_fee_mxn"].mean().unstack("platform")
    zones = pivot.index.tolist()
    platforms = pivot.columns.tolist()
    x = range(len(zones))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 4), facecolor=BG)
    ax.set_facecolor(BG)
    for i, plat in enumerate(platforms):
        vals = pivot[plat].values
        offset = (i - 1) * width
        bars = ax.bar([xi + offset for xi in x], vals, width=width, color=COLORS.get(plat, "#888"), label=PLATFORM_LABELS.get(plat, plat))
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.5, f"${val:.0f}", ha="center", color=FG, fontsize=8)

    ax.set_xticks(list(x))
    ax.set_xticklabels(zones, color=FG)
    ax.set_title("Delivery Fee Promedio por Tipo de Zona (MXN)", color=FG, fontsize=12)
    ax.set_ylabel("MXN", color=FG)
    ax.tick_params(colors=FG)
    ax.legend(facecolor="#222", labelcolor=FG)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    b64 = _fig_to_base64(fig)
    plt.close(fig)
    return b64


def _chart_promo_frequency(df: pd.DataFrame) -> str:
    """Horizontal bar: discount frequency per platform."""
    success = df[df["scraping_status"] == "success"]
    freq = success.groupby("platform")["active_discount"].mean().mul(100)
    fig, ax = plt.subplots(figsize=(6, 3), facecolor=BG)
    ax.set_facecolor(BG)
    bars = ax.barh(
        [PLATFORM_LABELS.get(p, p) for p in freq.index],
        freq.values,
        color=[COLORS.get(p, "#888") for p in freq.index],
        height=0.4,
    )
    for bar, val in zip(bars, freq.values):
        ax.text(val + 0.5, bar.get_y() + bar.get_height() / 2, f"{val:.1f}%", va="center", color=FG, fontsize=10)
    ax.set_title("Frecuencia de Descuentos Activos por Plataforma (%)", color=FG, fontsize=12)
    ax.set_xlabel("%", color=FG)
    ax.tick_params(colors=FG)
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")
    b64 = _fig_to_base64(fig)
    plt.close(fig)
    return b64


PLATFORM_LABELS = {"rappi": "Rappi", "ubereats": "Uber Eats", "didifood": "DiDi Food"}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rappi Competitive Intelligence — Informe Ejecutivo</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0F0F0F; color: #CCCCCC; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; }}
  .page {{ max-width: 960px; margin: 0 auto; padding: 2rem; }}
  h1 {{ color: #FF441A; font-size: 2rem; margin-bottom: 0.5rem; }}
  h2 {{ color: #FFFFFF; font-size: 1.3rem; margin: 2rem 0 0.8rem; border-bottom: 2px solid #FF441A; padding-bottom: 0.3rem; }}
  h3 {{ color: #FF441A; font-size: 1rem; margin: 1rem 0 0.3rem; }}
  p {{ line-height: 1.6; margin-bottom: 0.8rem; color: #CCCCCC; }}
  .cover {{ background: #1A1A1A; border-radius: 8px; padding: 2rem; margin-bottom: 2rem; border-top: 4px solid #FF441A; }}
  .cover .meta {{ color: #888; font-size: 0.85rem; margin-top: 0.5rem; }}
  .insight-card {{ background: #1A1A1A; border-radius: 6px; padding: 1.2rem; margin-bottom: 1rem; border-left: 4px solid #FF441A; }}
  .insight-card .label {{ font-weight: bold; color: #FF441A; }}
  .insight-card .priority {{ float: right; font-size: 0.8rem; padding: 2px 8px; border-radius: 10px; }}
  .priority-alta {{ background: #FF444444; color: #FF4444; }}
  .priority-media {{ background: #FFAA0044; color: #FFAA00; }}
  .chart-row {{ display: flex; gap: 1rem; margin: 1rem 0; flex-wrap: wrap; }}
  .chart-box {{ background: #1A1A1A; border-radius: 6px; padding: 1rem; flex: 1; min-width: 280px; }}
  .chart-box img {{ width: 100%; border-radius: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th {{ background: #FF441A; color: #FFF; padding: 8px 12px; text-align: left; font-size: 0.85rem; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #222; font-size: 0.85rem; }}
  tr:hover {{ background: #1F1F1F; }}
  .metric-box {{ background: #1A1A1A; border-radius: 6px; padding: 1rem; display: inline-block; margin: 0.3rem; text-align: center; min-width: 140px; }}
  .metric-box .val {{ font-size: 1.5rem; font-weight: bold; color: #FF441A; }}
  .metric-box .lbl {{ font-size: 0.75rem; color: #888; }}
  .metrics-row {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1rem 0; }}
  .limitations {{ background: #1A1A1A; border-radius: 6px; padding: 1.2rem; border-left: 4px solid #888; }}
  footer {{ margin-top: 3rem; color: #444; font-size: 0.75rem; text-align: center; border-top: 1px solid #222; padding-top: 1rem; }}
  ul {{ padding-left: 1.5rem; line-height: 1.8; }}
  li {{ color: #CCCCCC; }}
</style>
</head>
<body>
<div class="page">

<div class="cover">
  <h1>🟠 Rappi Competitive Intelligence</h1>
  <h2 style="border:none;color:#CCCCCC;">Informe Ejecutivo de Análisis Competitivo</h2>
  <p class="meta">
    Fecha: {date} &nbsp;|&nbsp; Modo: {mode} &nbsp;|&nbsp;
    {total_records:,} registros analizados &nbsp;|&nbsp; {platforms} plataformas &nbsp;|&nbsp; {addresses} direcciones
  </p>
  <p style="margin-top:0.8rem;color:#888;font-size:0.85rem;">
    Metodología: {methodology}
  </p>
</div>

<h2>1. Metodología y Scope</h2>
<p>
  Se recolectaron datos de precios, delivery fees, service fees, tiempos de entrega y
  descuentos activos de las tres principales plataformas de delivery en México: Rappi, Uber Eats y DiDi Food.
  El análisis cubre <strong>{addresses} direcciones estratégicas</strong> distribuidas en CDMX (zonas premium,
  media y periférica), Guadalajara, Monterrey y 5 ciudades secundarias.
</p>
<p>
  Para cada dirección se evaluaron <strong>{product_count} productos de referencia</strong>
  (Big Mac, Whopper, Combos, Coca-Cola 500ml, Agua Bonafont 1L, Pañales Huggies)
  seleccionados por ser comparables entre plataformas.
</p>

<div class="metrics-row">
  <div class="metric-box"><div class="val">{total_records:,}</div><div class="lbl">Registros Analizados</div></div>
  <div class="metric-box"><div class="val">{success_records:,}</div><div class="lbl">Registros Exitosos</div></div>
  <div class="metric-box"><div class="val">{addresses}</div><div class="lbl">Direcciones</div></div>
  <div class="metric-box"><div class="val">{platforms}</div><div class="lbl">Plataformas</div></div>
  <div class="metric-box"><div class="val">{product_count}</div><div class="lbl">Productos</div></div>
  <div class="metric-box"><div class="val">{cities}</div><div class="lbl">Ciudades</div></div>
</div>

<h2>2. Análisis Comparativo</h2>

<h3>2.1 Posicionamiento de Precios</h3>
{price_table}

<h3>2.2 Estructura de Fees</h3>
{fee_table}

<h3>2.3 Tiempo de Entrega</h3>
{time_table}

<h3>2.4 Visualizaciones Clave</h3>
<div class="chart-row">
  <div class="chart-box">
    <p style="color:#FF441A;font-weight:bold;margin-bottom:0.5rem;">Precio Promedio por Plataforma</p>
    <img src="data:image/png;base64,{chart_price}" alt="Price comparison">
  </div>
  <div class="chart-box">
    <p style="color:#FF441A;font-weight:bold;margin-bottom:0.5rem;">Delivery Fee por Zona</p>
    <img src="data:image/png;base64,{chart_fee_zone}" alt="Fee by zone">
  </div>
</div>
<div class="chart-row">
  <div class="chart-box">
    <p style="color:#FF441A;font-weight:bold;margin-bottom:0.5rem;">Agresividad Promocional</p>
    <img src="data:image/png;base64,{chart_promo}" alt="Promo frequency">
  </div>
</div>

<h2>3. Top 5 Insights Accionables</h2>
{insights_html}

<h2>4. Consideraciones Éticas y Limitaciones</h2>
<div class="limitations">
<ul>
  <li><strong>Robots.txt:</strong> Los scrapers respetan los archivos robots.txt de cada plataforma cuando es posible.</li>
  <li><strong>Rate Limiting:</strong> Delays aleatorios de 2-5 segundos entre requests para no sobrecargar servidores.</li>
  <li><strong>User-Agents:</strong> Se usan User-Agents reales de navegadores comunes para simular tráfico legítimo.</li>
  <li><strong>Términos de Servicio:</strong> Este análisis es para fines de inteligencia competitiva interna. Consultar con Legal antes de implementación sistemática en producción.</li>
  <li><strong>Disponibilidad de datos:</strong> Los precios pueden variar en tiempo real; los datos representan un snapshot del momento de scraping.</li>
  <li><strong>Bloqueos:</strong> Las plataformas pueden implementar anti-scraping; en modo mock se usan datos sintéticos estadísticamente realistas como fallback.</li>
  <li><strong>Cobertura:</strong> No todos los restaurantes están disponibles en todas las zonas; ~5% de datos faltantes es esperado.</li>
</ul>
</div>

<h2>5. Próximos Pasos</h2>
<ul>
  <li>Automatizar scraping con cron job diario para análisis de tendencias temporales.</li>
  <li>Integrar PedidosYa e iFood para mayor cobertura competitiva.</li>
  <li>Implementar alertas automáticas cuando competidores bajen precios >10% en zonas estratégicas.</li>
  <li>Expandir cobertura a 50+ ciudades secundarias en México.</li>
  <li>Desarrollar modelo predictivo de pricing competitivo usando series de tiempo.</li>
  <li>Escalar a ScraperAPI (~$49/mes) si los sitios implementan bloqueos sistemáticos.</li>
</ul>

<footer>
  Datos recolectados el {date} | Modo: {mode} | Rappi Competitive Intelligence System v1.0<br>
  Este informe es confidencial y de uso interno exclusivo de los equipos de Pricing, Operations y Strategy de Rappi.
</footer>

</div>
</body>
</html>"""


def _build_price_table(df: pd.DataFrame) -> str:
    success = df[df["scraping_status"] == "success"]
    stats = success.groupby("platform").agg(
        avg_price=("product_price_mxn", "mean"),
        min_price=("product_price_mxn", "min"),
        max_price=("product_price_mxn", "max"),
    ).round(2)
    rows = "".join(
        f"<tr><td>{PLATFORM_LABELS.get(p, p)}</td><td>${r['avg_price']:.2f}</td>"
        f"<td>${r['min_price']:.2f}</td><td>${r['max_price']:.2f}</td></tr>"
        for p, r in stats.iterrows()
    )
    return f"""<table><tr><th>Plataforma</th><th>Precio Prom. (MXN)</th>
    <th>Precio Mín.</th><th>Precio Máx.</th></tr>{rows}</table>"""


def _build_fee_table(df: pd.DataFrame) -> str:
    success = df[df["scraping_status"] == "success"]
    stats = success.groupby("platform").agg(
        avg_delivery=("delivery_fee_mxn", "mean"),
        avg_service=("service_fee_mxn", "mean"),
        avg_total=("total_price_mxn", "mean"),
    ).round(2)
    rows = "".join(
        f"<tr><td>{PLATFORM_LABELS.get(p, p)}</td><td>${r['avg_delivery']:.2f}</td>"
        f"<td>${r['avg_service']:.2f}</td><td>${r['avg_total']:.2f}</td></tr>"
        for p, r in stats.iterrows()
    )
    return f"""<table><tr><th>Plataforma</th><th>Delivery Fee Prom.</th>
    <th>Service Fee Prom.</th><th>Total Prom.</th></tr>{rows}</table>"""


def _build_time_table(df: pd.DataFrame) -> str:
    success = df[df["scraping_status"] == "success"].dropna(
        subset=["estimated_delivery_min", "estimated_delivery_max"]
    )
    if len(success) == 0:
        return "<p>Datos de tiempo no disponibles.</p>"
    success = success.copy()
    success["midpoint"] = (success["estimated_delivery_min"] + success["estimated_delivery_max"]) / 2
    stats = success.groupby("platform")["midpoint"].mean().round(1)
    rows = "".join(
        f"<tr><td>{PLATFORM_LABELS.get(p, p)}</td><td>{v:.1f} min</td></tr>"
        for p, v in stats.items()
    )
    return f"<table><tr><th>Plataforma</th><th>Tiempo Estimado Promedio</th></tr>{rows}</table>"


def _build_insights_html(insights: list[dict]) -> str:
    html_parts = []
    for ins in insights:
        priority = ins.get("priority", "baja")
        pclass = f"priority-{priority}"
        html_parts.append(f"""
        <div class="insight-card">
          <div>
            <span class="label">#{ins['insight_id']} {ins['title']}</span>
            <span class="priority {pclass}">{priority.upper()}</span>
          </div>
          <p style="margin-top:0.8rem;"><strong>Finding:</strong> {ins['finding']}</p>
          <p><strong>Impacto:</strong> {ins['impact']}</p>
          <p><strong>Recomendación:</strong> {ins['recommendation']}</p>
          <p style="color:#FFAA00;font-size:0.85rem;">📊 {ins['supporting_metric']}</p>
        </div>""")
    return "\n".join(html_parts)


def generate_report(df: pd.DataFrame, insights: list[dict] | None = None) -> str:
    """Generate an executive HTML report and save it to reports/.

    Args:
        df: Processed DataFrame with competitive data.
        insights: Pre-generated insights list. Generated automatically if None.

    Returns:
        Absolute path to the generated HTML file.
    """
    from analysis.insights_generator import generate_top5_insights

    if insights is None:
        success_df = df[df["scraping_status"] == "success"]
        insights = generate_top5_insights(success_df)

    success_df = df[df["scraping_status"] == "success"]
    now = datetime.datetime.utcnow()
    mode = df["scraping_mode"].iloc[0] if "scraping_mode" in df.columns and len(df) > 0 else "unknown"

    chart_price = _chart_price_comparison(success_df)
    chart_fee_zone = _chart_delivery_fee_by_zone(success_df)
    chart_promo = _chart_promo_frequency(success_df)

    html = HTML_TEMPLATE.format(
        date=now.strftime("%Y-%m-%d %H:%M UTC"),
        mode=mode.upper(),
        total_records=len(df),
        success_records=len(success_df),
        platforms=df["platform"].nunique() if "platform" in df.columns else 3,
        addresses=df["address_id"].nunique() if "address_id" in df.columns else 30,
        product_count=df["product_name"].nunique() if "product_name" in df.columns else 8,
        cities=df["city"].nunique() if "city" in df.columns else 8,
        methodology=(
            "Playwright + playwright-stealth (producción) / datos sintéticos estadísticamente realistas (mock). "
            "Rate limiting 2-5s entre requests. Retry con backoff exponencial."
        ),
        price_table=_build_price_table(success_df),
        fee_table=_build_fee_table(success_df),
        time_table=_build_time_table(success_df),
        chart_price=chart_price,
        chart_fee_zone=chart_fee_zone,
        chart_promo=chart_promo,
        insights_html=_build_insights_html(insights),
    )

    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / f"competitive_report_{now.strftime('%Y%m%d_%H%M%S')}.html"
    report_path.write_text(html, encoding="utf-8")
    return str(report_path)

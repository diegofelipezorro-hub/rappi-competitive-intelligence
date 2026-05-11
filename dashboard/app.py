"""Streamlit dashboard — Rappi Competitive Intelligence War Room.

4 tabs: Executive Overview, Geographic Analysis, Product Comparison, Top 5 Insights.
Light theme with Rappi brand colors.
"""

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Allow running from repo root
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from analysis.comparator import (
    compute_price_index,
    compute_delivery_fee_by_zone,
    compute_delivery_fee_by_city,
    compute_delivery_time_comparison,
    compute_coverage,
    compute_promotional_aggressiveness,
    compute_total_cost_comparison,
    compute_rappi_competitiveness_gap,
    PLATFORM_LABELS,
)
from analysis.insights_generator import generate_top5_insights

# ── Brand colors ────────────────────────────────────────────────────────────
COLORS = {
    "rappi": "#FF441A",
    "ubereats": "#06C167",
    "didifood": "#FF6B35",
    "background": "#FFFFFF",
    "card": "#F7F7F7",
    "text": "#1A1A1A",
    "muted": "#666666",
}

PLATFORM_COLOR_MAP = {
    "rappi": COLORS["rappi"],
    "ubereats": COLORS["ubereats"],
    "didifood": COLORS["didifood"],
}

ZONE_DISPLAY = {"premium": "Premium", "media": "Media", "periferica": "Periférica"}
CITY_DISPLAY = {
    "cdmx": "CDMX", "guadalajara": "Guadalajara", "monterrey": "Monterrey",
    "puebla": "Puebla", "tijuana": "Tijuana", "leon": "León",
    "merida": "Mérida", "cancun": "Cancún",
}

st.set_page_config(
    page_title="Rappi Competitive Intelligence",
    page_icon="🟠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS — light theme
st.markdown(
    """
    <style>
    .main { background-color: #FFFFFF; color: #1A1A1A; }
    .block-container { padding-top: 1rem; }
    .metric-card {
        background: #F7F7F7;
        border-radius: 8px;
        padding: 1rem 1.5rem;
        border-left: 4px solid #FF441A;
        margin-bottom: 0.5rem;
        color: #1A1A1A;
    }
    .insight-card {
        background: #F7F7F7;
        border-radius: 8px;
        padding: 1.2rem 1.5rem;
        margin-bottom: 1rem;
        border-top: 3px solid #FF441A;
        color: #1A1A1A;
    }
    .priority-alta { color: #CC0000; font-weight: bold; }
    .priority-media { color: #CC7700; font-weight: bold; }
    .priority-baja { color: #007700; font-weight: bold; }
    h1, h2, h3 { color: #1A1A1A; }
    .stTabs [data-baseweb="tab"] { color: #666666; }
    .stTabs [aria-selected="true"] { color: #FF441A; }
    footer { color: #888888; font-size: 0.75rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Data loading ─────────────────────────────────────────────────────────────

_NUMERIC_COLS = [
    "product_price_mxn", "delivery_fee_mxn", "service_fee_mxn",
    "total_price_mxn", "estimated_delivery_min", "estimated_delivery_max",
    "discount_amount_mxn",
]


def _cast_numeric(df: pd.DataFrame) -> pd.DataFrame:
    for col in _NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=3600)
def load_addresses() -> pd.DataFrame:
    path = ROOT / "config" / "addresses.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data["addresses"])


def _get_real_success_df(filtered_df: pd.DataFrame, selected_key: str) -> pd.DataFrame:
    """Return success records — in production mode, exclude mock_fallback rows."""
    if selected_key == "production":
        mask = (
            (filtered_df["scraping_status"] == "success") &
            (filtered_df["scraping_mode"] == "production")
        )
    else:
        mask = filtered_df["scraping_status"] == "success"
    return filtered_df[mask].copy()


@st.cache_data(ttl=300)
def load_available_data() -> dict:
    """Find the latest pure-mock CSV and the latest production CSV separately."""
    processed_dir = ROOT / "data" / "processed"
    csv_files = sorted(processed_dir.glob("competitive_data_*.csv"), reverse=True)
    result: dict = {"production": None, "mock": None}
    for f in csv_files:
        try:
            peek = pd.read_csv(f, nrows=1, encoding="utf-8")
            mode = peek["scraping_mode"].iloc[0] if "scraping_mode" in peek.columns else "unknown"
            if mode == "production":
                key = "production"
            elif mode == "mock":
                key = "mock"
            else:
                continue  # skip mock_fallback and unknown files
            if result[key] is None:
                result[key] = _cast_numeric(pd.read_csv(f, encoding="utf-8"))
        except Exception:
            pass
        if result["production"] is not None and result["mock"] is not None:
            break
    return result



def plotly_layout(fig: go.Figure, title: str = "", note: str = "") -> go.Figure:
    """Apply consistent light theme to a Plotly figure."""
    fig.for_each_trace(lambda t: t.update(name=PLATFORM_LABELS.get(t.name, t.name)))
    fig.update_layout(
        title=dict(text=title, font=dict(color="#1A1A1A", size=14)),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F7F7F7",
        font=dict(color="#333333"),
        legend=dict(bgcolor="#FFFFFF", bordercolor="#DDDDDD", borderwidth=1),
        margin=dict(l=40, r=20, t=50, b=60 if note else 40),
    )
    if note:
        fig.add_annotation(
            text=note,
            xref="paper", yref="paper",
            x=0, y=-0.15,
            showarrow=False,
            font=dict(size=10, color="#999999"),
        )
    return fig


# ── Header ───────────────────────────────────────────────────────────────────

st.markdown(
    '<h1 style="color:#FF441A;margin-bottom:0;">🟠 Rappi Competitive Intelligence</h1>',
    unsafe_allow_html=True,
)


available_data = load_available_data()

if available_data["production"] is None and available_data["mock"] is None:
    st.error(
        "No se encontraron datos procesados. "
        "Ejecuta primero: `python run_scraper.py --mode mock`"
    )
    st.stop()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:

    # — Data source selector —
    st.markdown("### 📂 Fuente de Datos")

    source_opts: dict[str, str] = {}
    if available_data["production"] is not None:
        _p = available_data["production"]
        _pts = str(_p["timestamp"].iloc[0])[:10]
        _pn = int((_p["scraping_status"] == "success").sum())
        source_opts[f"Producción — real ({_pts}, {_pn:,} ok)"] = "production"
    if available_data["mock"] is not None:
        _m = available_data["mock"]
        _mts = str(_m["timestamp"].iloc[0])[:10]
        _mn = len(_m)
        source_opts[f"Mock — prueba ({_mts}, {_mn:,} reg.)"] = "mock"
    if len(source_opts) == 2:
        source_opts["Ambos (comparación)"] = "all"

    selected_label = st.radio("Dataset activo", list(source_opts.keys()))
    selected_key = source_opts[selected_label]

    if selected_key == "production":
        df = available_data["production"]
    elif selected_key == "mock":
        df = available_data["mock"]
    else:
        df = pd.concat(
            [available_data["production"], available_data["mock"]],
            ignore_index=True,
        )

    st.markdown("---")

    # — Calidad de datos —
    st.markdown("### Calidad de Datos")
    st.markdown(
        '<div style="font-size:0.78rem;line-height:1.7;">'
        '<span style="color:#007700;font-weight:bold;">● Rappi</span> — Real (API directa, todas las ciudades)<br>'
        '<span style="color:#06C167;font-weight:bold;">● Uber Eats</span> — Real en CDMX · Simulado fuera<br>'
        '<span style="color:#CC7700;font-weight:bold;">● DiDi Food</span> — Simulado (app-only, requiere auth)'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # — Filters —
    st.markdown("### Filtros")
    cities = ["Todas"] + sorted(df["city"].dropna().unique().tolist())
    selected_city = st.selectbox("Ciudad", cities)
    zone_types = ["Todas"] + sorted(df["zone_type"].dropna().unique().tolist())
    selected_zone = st.selectbox("Tipo de Zona", zone_types)
    categories = ["Todas"] + sorted(df["product_category"].dropna().unique().tolist())
    selected_category = st.selectbox("Categoría", categories)
    products_list = ["Todos"] + sorted(df["product_name"].dropna().unique().tolist())
    selected_product = st.selectbox("Producto", products_list)

# — Metadata banner —
if selected_key == "all":
    scraping_mode = "producción + mock"
else:
    scraping_mode = df["scraping_mode"].iloc[0] if "scraping_mode" in df.columns else "unknown"
timestamp = df["timestamp"].iloc[0] if "timestamp" in df.columns else "N/A"
total_records = len(df)
success_records = int((df["scraping_status"] == "success").sum()) if "scraping_status" in df.columns else total_records

if selected_key == "all":
    st.warning(
        "⚠️ **Modo Ambos**: los promedios mezclan precios reales (producción) con precios "
        "sintéticos (mock). Útil solo para comparar cobertura entre datasets, no para análisis de precios."
    )

st.markdown(
    f'<p style="color:#666;font-size:0.85rem;">Dataset: <b>{scraping_mode.upper()}</b> | '
    f'{success_records:,}/{total_records:,} registros exitosos | Última actualización: {str(timestamp)[:19]}</p>',
    unsafe_allow_html=True,
)

# Apply filters
filtered_df = df.copy()
if selected_city != "Todas":
    filtered_df = filtered_df[filtered_df["city"] == selected_city]
if selected_zone != "Todas":
    filtered_df = filtered_df[filtered_df["zone_type"] == selected_zone]
if selected_category != "Todas":
    filtered_df = filtered_df[filtered_df["product_category"] == selected_category]
if selected_product != "Todos":
    filtered_df = filtered_df[filtered_df["product_name"] == selected_product]

success_df = _get_real_success_df(filtered_df, selected_key)

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📊 Executive Overview", "🗺️ Geographic Analysis", "🍔 Product Comparison", "💡 Top 5 Insights", "🔬 Cobertura & Metodología"]
)


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Executive Overview
# ════════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown("## Executive Overview")

    # KPI row
    price_idx = compute_price_index(success_df)
    fee_by_zone = compute_delivery_fee_by_zone(success_df)
    time_df = compute_delivery_time_comparison(success_df)

    platforms_in_analysis = set(success_df["platform"].unique()) if len(success_df) > 0 else set()

    kpi_cols = st.columns(3)
    for i, platform in enumerate(["rappi", "ubereats", "didifood"]):
        label = PLATFORM_LABELS.get(platform, platform)
        color = COLORS[platform]
        with kpi_cols[i]:
            if platform not in platforms_in_analysis:
                note = "Sin datos reales — simulado (excluido en modo Producción)" if selected_key == "production" else "Sin datos"
                st.markdown(
                    f'<div class="metric-card" style="border-left-color:{color};opacity:0.55;">'
                    f'<div style="color:{color};font-size:1.1rem;font-weight:bold;">{label}</div>'
                    f'<div style="color:#888;font-style:italic;font-size:0.85rem;">{note}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                continue
            row = price_idx[price_idx["platform"] == platform]
            avg_price = row["avg_price_mxn"].values[0] if len(row) > 0 else 0
            avg_fee_row = fee_by_zone[fee_by_zone["platform"] == platform]["delivery_fee_mxn"]
            avg_fee = avg_fee_row.mean() if len(avg_fee_row) > 0 else 0
            time_row = time_df[time_df["platform"] == platform]["delivery_midpoint"]
            avg_time = time_row.mean() if len(time_row) > 0 else 0
            st.markdown(
                f"""<div class="metric-card" style="border-left-color:{color};">
                <div style="color:{color};font-size:1.1rem;font-weight:bold;">{label}</div>
                <div>Precio prod: <b>&#36;{avg_price:.0f} MXN</b></div>
                <div>Delivery fee: <b>&#36;{avg_fee:.0f} MXN</b></div>
                <div>Tiempo est.: <b>{avg_time:.0f} min</b></div>
                </div>""",
                unsafe_allow_html=True,
            )

    if selected_key == "production" and "didifood" not in platforms_in_analysis:
        st.info(
            "ℹ️ **DiDi Food no aparece en modo Producción** — su app requiere autenticación, "
            "por lo que solo existen datos simulados para esta plataforma. "
            "Cambia a **Mock** en el selector de datos para ver el análisis comparativo completo."
        )

    st.markdown("---")

    # Traffic light — compare Rappi vs cheapest competitor
    rappi_row = price_idx[price_idx["platform"] == "rappi"]
    competitors = price_idx[price_idx["platform"] != "rappi"]
    st.markdown("### ¿Rappi es competitivo en precio de producto?")
    if len(rappi_row) > 0 and len(competitors) > 0:
        rappi_avg = rappi_row["avg_price_mxn"].values[0]
        cheapest = competitors.loc[competitors["avg_price_mxn"].idxmin()]
        cheapest_avg = cheapest["avg_price_mxn"]
        cheapest_label = PLATFORM_LABELS.get(cheapest["platform"], cheapest["platform"])
        gap_pct = (rappi_avg - cheapest_avg) / cheapest_avg * 100
        if gap_pct <= 0:
            tl_color, tl_text = "#007700", "🟢 MÁS BARATO"
        elif gap_pct <= 5:
            tl_color, tl_text = "#CC7700", "🟡 PRECIO SIMILAR"
        else:
            tl_color, tl_text = "#CC0000", "🔴 MÁS CARO"
        st.markdown(
            f'<span style="color:{tl_color};font-size:2rem;">{tl_text}</span>'
            f'<p style="margin-top:0.5rem;font-size:1rem;color:#333;">'
            f'Rappi: <b>&#36;{rappi_avg:.0f} MXN</b> promedio &nbsp;·&nbsp; '
            f'{cheapest_label} <span style="color:#666;">(más barato)</span>: <b>&#36;{cheapest_avg:.0f} MXN</b>'
            f' &nbsp;·&nbsp; Rappi es <b style="color:{tl_color};">{gap_pct:+.1f}%</b>'
            f' respecto a la alternativa más económica</p>',
            unsafe_allow_html=True,
        )
    elif len(rappi_row) > 0:
        rappi_avg = rappi_row["avg_price_mxn"].values[0]
        st.markdown(
            f'<p style="font-size:1rem;color:#333;">Solo Rappi disponible en los datos actuales'
            f' — precio promedio: <b>&#36;{rappi_avg:.0f} MXN</b></p>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    col_left, col_right = st.columns(2)

    # Total cost comparison bar chart
    with col_left:
        total_cost = compute_total_cost_comparison(success_df)
        if len(total_cost) > 0:
            fig = px.bar(
                total_cost,
                y="product_name",
                x="total_price_mxn",
                color="platform",
                barmode="group",
                orientation="h",
                color_discrete_map=PLATFORM_COLOR_MAP,
                labels={"total_price_mxn": "Precio Total (MXN)", "product_name": "Producto", "platform": "Plataforma"},
            )
            fig = plotly_layout(
                fig,
                title="Precio Total (producto + fees) por Plataforma",
                note=f"Fuente: datos {scraping_mode.upper()} | {str(timestamp)[:10]}",
            )
            fig.update_layout(height=380, yaxis=dict(automargin=True))
            st.plotly_chart(fig, use_container_width=True)

    # Price index bar chart
    with col_right:
        if len(price_idx) > 0:
            price_idx["platform_label"] = price_idx["platform"].map(PLATFORM_LABELS)
            fig2 = px.bar(
                price_idx,
                x="platform_label",
                y="price_index",
                color="platform",
                color_discrete_map=PLATFORM_COLOR_MAP,
                labels={"price_index": "Índice de Precio", "platform_label": "Plataforma"},
                text="price_index",
            )
            fig2.add_hline(y=100, line_dash="dash", line_color="#888888", annotation_text="Rappi base")
            fig2 = plotly_layout(fig2, title="Índice de Precio por Plataforma (Rappi = 100)")
            fig2.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            st.plotly_chart(fig2, use_container_width=True)

    # Promotional aggressiveness
    promo_df = compute_promotional_aggressiveness(success_df)
    if len(promo_df) > 0:
        st.markdown("### Agresividad Promocional")
        fig3 = px.bar(
            promo_df,
            x="platform_label",
            y="discount_frequency_pct",
            color="platform",
            color_discrete_map=PLATFORM_COLOR_MAP,
            labels={"discount_frequency_pct": "% Visitas con Descuento", "platform_label": "Plataforma"},
            text="discount_frequency_pct",
        )
        fig3 = plotly_layout(fig3, title="Frecuencia de Descuentos Activos por Plataforma (%)")
        fig3.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        st.plotly_chart(fig3, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Geographic Analysis
# ════════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("## Geographic Analysis")

    col_geo1, col_geo2 = st.columns(2)

    # Delivery fee by zone type
    with col_geo1:
        fee_zone = compute_delivery_fee_by_zone(success_df)
        if len(fee_zone) > 0:
            fee_zone["zone_label"] = fee_zone["zone_type"].map(ZONE_DISPLAY).fillna(fee_zone["zone_type"])
            fig_fee = px.bar(
                fee_zone,
                x="zone_label",
                y="delivery_fee_mxn",
                color="platform",
                barmode="group",
                color_discrete_map=PLATFORM_COLOR_MAP,
                labels={
                    "delivery_fee_mxn": "Delivery Fee Prom. (MXN)",
                    "zone_label": "Tipo de Zona",
                    "platform": "Plataforma",
                },
            )
            fig_fee = plotly_layout(
                fig_fee,
                title="Delivery Fee Promedio por Zona y Plataforma",
                note="Premium = Polanco/San Pedro | Media = Del Valle/GDL Centro | Periférica = Ecatepec/Nezahualcóyotl",
            )
            st.plotly_chart(fig_fee, use_container_width=True)

    # Delivery fee by city
    with col_geo2:
        fee_city = compute_delivery_fee_by_city(success_df)
        if len(fee_city) > 0:
            fee_city["city_label"] = fee_city["city"].map(CITY_DISPLAY).fillna(fee_city["city"].str.title())
            fig_city = px.bar(
                fee_city,
                x="city_label",
                y="delivery_fee_mxn",
                color="platform",
                barmode="group",
                color_discrete_map=PLATFORM_COLOR_MAP,
                labels={
                    "delivery_fee_mxn": "Delivery Fee Prom. (MXN)",
                    "city_label": "Ciudad",
                    "platform": "Plataforma",
                },
            )
            fig_city = plotly_layout(fig_city, title="Delivery Fee Promedio por Ciudad")
            fig_city.update_xaxes(tickangle=45, automargin=True)
            st.plotly_chart(fig_city, use_container_width=True)

    # Heatmap: price index by zone × platform
    st.markdown("### Heatmap — Índice de Precio por Zona y Plataforma")
    try:
        pivot_data = success_df.groupby(["zone_type", "platform"])["product_price_mxn"].mean().unstack("platform")
        if "rappi" in pivot_data.columns:
            rappi_base = pivot_data["rappi"].copy()
            for col in pivot_data.columns:
                pivot_data[col] = (pivot_data[col] / rappi_base * 100).round(1)
            pivot_data.columns = [PLATFORM_LABELS.get(c, c) for c in pivot_data.columns]
            pivot_data.index = [ZONE_DISPLAY.get(z, z) for z in pivot_data.index]
            fig_heat = px.imshow(
                pivot_data,
                color_continuous_scale=[[0, "#44BB66"], [0.4, "#FFCC00"], [1, "#FF4444"]],
                labels={"x": "Plataforma", "y": "Zona", "color": "Índice (Rappi=100)"},
                text_auto=True,
                zmin=80,
                zmax=115,
            )
            fig_heat = plotly_layout(
                fig_heat,
                title="Índice de Precio por Zona y Plataforma (Rappi = 100)",
            )
            st.plotly_chart(fig_heat, use_container_width=True)
    except Exception as e:
        st.warning(f"Heatmap no disponible con la selección actual: {e}")

    # Worst competitiveness zone callout
    try:
        gap = compute_rappi_competitiveness_gap(success_df)
        zone_label = ZONE_DISPLAY.get(gap["worst_zone"], gap["worst_zone"].capitalize())
        gap_sign = "más caro" if gap["gap_mxn"] > 0 else "más barato"
        card_color = "#CC0000" if gap["gap_mxn"] > 0 else "#007700"
        card_bg = "#FFF5F5" if gap["gap_mxn"] > 0 else "#F0FFF0"
        icon = "⚠️" if gap["gap_mxn"] > 0 else "✅"
        st.markdown(
            f"""<div class="metric-card" style="border-left-color:{card_color};background:{card_bg};">
            {icon} <b>Zona con mayor diferencial de delivery fee:</b> {zone_label}<br>
            Rappi: <b>&#36;{gap['rappi_fee']:.0f} MXN</b> · Mejor competidor: <b>&#36;{gap['competitor_fee']:.0f} MXN</b>
            · Rappi es <b>&#36;{abs(gap['gap_mxn']):.0f} MXN {gap_sign} ({abs(gap['gap_pct']):.0f}%)</b>
            </div>""",
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    # Delivery time by city
    time_data = compute_delivery_time_comparison(success_df)
    if len(time_data) > 0:
        st.markdown("### Tiempo de Entrega por Ciudad y Plataforma")
        time_data["city_label"] = time_data["city"].map(CITY_DISPLAY).fillna(time_data["city"].str.title())
        fig_time = px.bar(
            time_data,
            x="city_label",
            y="delivery_midpoint",
            color="platform",
            barmode="group",
            color_discrete_map=PLATFORM_COLOR_MAP,
            labels={"delivery_midpoint": "Tiempo Estimado (min)", "city_label": "Ciudad"},
        )
        fig_time = plotly_layout(fig_time, title="Tiempo Estimado de Entrega (minutos) por Ciudad")
        fig_time.update_xaxes(tickangle=45, automargin=True)
        st.plotly_chart(fig_time, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Product Comparison
# ════════════════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("## Product Comparison")

    # Scatter: product price vs delivery fee
    if len(success_df) > 0:
        fig_scatter = px.scatter(
            success_df,
            x="product_price_mxn",
            y="delivery_fee_mxn",
            color="platform",
            symbol="product_category",
            hover_data=["product_name", "city", "zone_type"],
            color_discrete_map=PLATFORM_COLOR_MAP,
            labels={
                "product_price_mxn": "Precio Producto (MXN)",
                "delivery_fee_mxn": "Delivery Fee (MXN)",
                "platform": "Plataforma",
            },
        )
        fig_scatter = plotly_layout(
            fig_scatter,
            title="Precio Producto vs Delivery Fee por Plataforma",
            note="Punto ideal: abajo-izquierda (precio bajo + fee bajo)",
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    # Product comparison table
    st.markdown("### Tabla Comparativa por Producto")
    total_cost = compute_total_cost_comparison(success_df)
    if len(total_cost) > 0:
        pivot_table = total_cost.pivot(index="product_name", columns="platform_label", values="total_price_mxn")
        pivot_table.columns.name = None
        pivot_table.index.name = "Producto"
        pivot_table = pivot_table.round(2)
        st.dataframe(
            pivot_table.style.background_gradient(cmap="RdYlGn_r", axis=1),
            use_container_width=True,
        )

    # Product price breakdown
    st.markdown("### Desglose de Costos por Plataforma")
    cost_breakdown = success_df.groupby("platform")[
        ["product_price_mxn", "delivery_fee_mxn", "service_fee_mxn"]
    ].mean().round(2).reset_index()
    cost_breakdown["platform_label"] = cost_breakdown["platform"].map(PLATFORM_LABELS)
    cost_melt = cost_breakdown.melt(
        id_vars=["platform", "platform_label"],
        value_vars=["product_price_mxn", "delivery_fee_mxn", "service_fee_mxn"],
        var_name="Componente",
        value_name="Monto (MXN)",
    )
    rename_map = {
        "product_price_mxn": "Precio Producto",
        "delivery_fee_mxn": "Delivery Fee",
        "service_fee_mxn": "Service Fee",
    }
    cost_melt["Componente"] = cost_melt["Componente"].map(rename_map)
    fig_stack = px.bar(
        cost_melt,
        x="platform_label",
        y="Monto (MXN)",
        color="Componente",
        barmode="stack",
        color_discrete_sequence=["#FF441A", "#FF8C00", "#FFCC00"],
        labels={"platform_label": "Plataforma"},
    )
    fig_stack = plotly_layout(fig_stack, title="Desglose de Costo Total Promedio por Plataforma")
    st.plotly_chart(fig_stack, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Top 5 Insights
# ════════════════════════════════════════════════════════════════════════════

with tab4:
    st.markdown("## Top 5 Insights Accionables")
    st.markdown(
        '<p style="color:#888;">Generado automáticamente a partir del análisis comparativo. '
        'Prioridad: <span class="priority-alta">ALTA</span> = acción inmediata | '
        '<span class="priority-media">MEDIA</span> = próximo sprint</p>',
        unsafe_allow_html=True,
    )

    try:
        insights = generate_top5_insights(success_df)
    except Exception as e:
        st.error(f"Error generando insights: {e}")
        insights = []

    priority_class = {"alta": "priority-alta", "media": "priority-media", "baja": "priority-baja"}

    for ins in insights:
        pclass = priority_class.get(ins.get("priority", "baja"), "priority-baja")
        st.markdown(
            f"""<div class="insight-card">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#FF441A;font-size:1.1rem;font-weight:bold;">#{ins['insight_id']} {ins['title']}</span>
                <span class="{pclass}">● {ins.get('priority','').upper()}</span>
            </div>
            <br>
            <b>🔍 Finding:</b> {ins['finding']}<br><br>
            <b>📈 Impacto:</b> {ins['impact']}<br><br>
            <b>✅ Recomendación:</b> {ins['recommendation']}<br><br>
            <div style="background:#FFF3E0;padding:0.5rem 1rem;border-radius:4px;color:#CC6600;">
                📊 {ins['supporting_metric']}
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Export button
    if st.button("📄 Exportar Informe HTML", type="primary"):
        try:
            sys.path.insert(0, str(ROOT))
            from reports.report_generator import generate_report
            report_path = generate_report(success_df, insights)
            st.success(f"Informe generado: `{report_path}`")
            with open(report_path, "r", encoding="utf-8") as f:
                html_content = f.read()
            st.download_button(
                label="⬇️ Descargar Informe HTML",
                data=html_content,
                file_name="rappi_competitive_intelligence_report.html",
                mime="text/html",
            )
        except Exception as e:
            st.error(f"Error generando informe: {e}")

# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Cobertura & Metodología
# ════════════════════════════════════════════════════════════════════════════

_CITY_LABELS = {
    "cdmx": "CDMX", "guadalajara": "Guadalajara", "monterrey": "Monterrey",
    "puebla": "Puebla", "tijuana": "Tijuana", "leon": "León",
    "merida": "Mérida", "cancun": "Cancún",
}
_ZONE_LABELS = {"premium": "Premium", "media": "Media", "periferica": "Periférica"}
_STATUS_COLORS = {"success": "#007700", "mock_fallback": "#CC7700", "unavailable": "#CC0000"}
_STATUS_LABELS = {"success": "Exitoso", "mock_fallback": "Mock Fallback", "unavailable": "No disponible"}

_ZONE_META = {
    "premium": {
        "icon": "🏙️",
        "title": "Zonas Premium",
        "why": (
            "Ticket promedio más alto, usuarios con menor sensibilidad al precio. "
            "Son el benchmark de pricing máximo — si Rappi no es competitivo aquí, "
            "el problema es estructural. Incluye Polanco, Roma Norte, San Pedro GG, Zapopan Vallarta y Cancún turístico."
        ),
    },
    "media": {
        "icon": "🏘️",
        "title": "Zonas Media",
        "why": (
            "Mayor volumen de usuarios activos en México. Sensibilidad media-alta al precio. "
            "Representan el core del GMV de Rappi. "
            "Incluye Del Valle, Coapa, Centro MTY, GDL Americana y ciudades secundarias (Puebla, Tijuana, León, Mérida)."
        ),
    },
    "periferica": {
        "icon": "🏗️",
        "title": "Zonas Periféricas",
        "why": (
            "Mayor brecha de cobertura vs competidores. Usuarios muy price-sensitive. "
            "Son el mercado de mayor potencial de crecimiento donde DiDi Food compite más agresivamente. "
            "Incluye Ecatepec, Atizapán, Naucalpan, Pedregal, Nezahualcóyotl y Tlaquepaque."
        ),
    },
}

with tab5:
    st.markdown("## Cobertura del Scraping & Metodología")

    prod_df = available_data["production"]

    if prod_df is None:
        st.warning(
            "No hay datos de producción disponibles. "
            "Ejecuta: `python run_scraper.py --mode production`"
        )
    else:
        # ── 0. Calidad de datos ───────────────────────────────────────────
        st.markdown("### Calidad y Origen de los Datos")
        st.markdown(
            "Este sistema recolecta datos de tres plataformas con distintos niveles de acceso. "
            "La siguiente tabla documenta el origen real de cada dato mostrado en el dashboard."
        )

        q1, q2, q3 = st.columns(3)
        for col, plat, color, source, status, detail in [
            (
                q1, "Rappi", "#FF441A",
                "API interna (requests HTTP)",
                "Datos 100% reales",
                "SSG HTML + Search API descubierta por network interception. "
                "Sin Playwright. Funciona en las 8 ciudades analizadas.",
            ),
            (
                q2, "Uber Eats", "#06C167",
                "API interna (requests HTTP)",
                "Real en CDMX · Simulado en otras ciudades",
                "APIs getFeedV1 / getStoreV1 descubiertas por network interception. "
                "Solo devuelve tiendas reales dentro de un radio de 60 km — "
                "fuera de CDMX no se encontraron tiendas; se usan datos simulados para completar el modelo.",
            ),
            (
                q3, "DiDi Food", "#CC7700",
                "Datos simulados (mock)",
                "Sin datos reales — incluido para el caso de uso",
                "La app requiere autenticación (cookie ticket en .c.didi-food.com). "
                "Las firmas anti-bot wsgsig son generadas por un SDK JS ofuscado irreproducible. "
                "Se incluye en el análisis con datos estadísticamente realistas para simular "
                "un escenario competitivo completo. En producción real se reemplazaría con datos de la app móvil.",
            ),
        ]:
            col.markdown(
                f'<div class="insight-card" style="border-top-color:{color};">'
                f'<div style="color:{color};font-weight:bold;font-size:1rem;">{plat}</div>'
                f'<div style="font-size:0.75rem;color:#888;margin:0.3rem 0;">Fuente: {source}</div>'
                f'<div style="font-size:0.8rem;font-weight:bold;margin-bottom:0.4rem;">{status}</div>'
                f'<div style="font-size:0.8rem;color:#555;">{detail}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── 1. Metadata ───────────────────────────────────────────────────
        st.markdown("### Metadata del Scraping Real")

        _ts = str(prod_df["timestamp"].iloc[0])[:19] if "timestamp" in prod_df.columns else "N/A"
        _total = len(prod_df)
        _ok = int((prod_df["scraping_status"] == "success").sum())
        _fallback = int((prod_df["scraping_status"] == "mock_fallback").sum())
        _unavail = int((prod_df["scraping_status"] == "unavailable").sum())
        _cities_n = prod_df["city"].nunique()
        _plat_n = prod_df["platform"].nunique()

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        for col, label, val, color in [
            (m1, "Fecha scraping", _ts[:10], "#FF441A"),
            (m2, "Total registros", f"{_total:,}", "#1A1A1A"),
            (m3, "Exitosos", f"{_ok:,} ({_ok*100//_total}%)", "#007700"),
            (m4, "Mock fallback", f"{_fallback:,}", "#CC7700"),
            (m5, "No disponibles", f"{_unavail:,}", "#CC0000"),
            (m6, "Ciudades", f"{_cities_n} / 8", "#0055CC"),
        ]:
            col.markdown(
                f'<div class="metric-card" style="border-left-color:{color};">'
                f'<div style="color:{color};font-size:0.75rem;font-weight:bold;">{label}</div>'
                f'<div style="font-size:1.1rem;font-weight:bold;">{val}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")

        # ── 2. Cobertura por plataforma × ciudad ─────────────────────────
        st.markdown("### Cobertura por Plataforma y Ciudad")
        st.caption("% de registros con scraping exitoso (precio real obtenido) sobre el total de intentos.")

        # "Precio real" = el campo product_price_mxn tiene un valor > 0.
        # Es el único criterio que no se puede falsificar: DiDi (siempre None)
        # y UberEats fuera de CDMX (None) aparecerán correctamente como 0%.
        cov_total = prod_df.groupby(["city", "platform"]).size().reset_index(name="total")
        cov_real = (
            prod_df[prod_df["product_price_mxn"].notna() & (prod_df["product_price_mxn"] > 0)]
            .groupby(["city", "platform"])
            .size()
            .reset_index(name="con_precio_real")
        )
        cov = cov_total.merge(cov_real, on=["city", "platform"], how="left").fillna(0)
        cov["real_pct"] = (cov["con_precio_real"] / cov["total"] * 100).round(0).astype(int)
        cov["city_label"] = cov["city"].map(_CITY_LABELS).fillna(cov["city"])
        cov["platform_label"] = cov["platform"].map(PLATFORM_LABELS).fillna(cov["platform"])

        st.info(
            "**Verde = precio real obtenido** (product_price_mxn > 0) | "
            "**Rojo = sin precio real** (mock fallback o no disponible). "
            "DiDi Food siempre 0% porque requiere autenticación. "
            "Uber Eats solo tiene datos reales en CDMX."
        )

        pivot_cov = cov.pivot(index="city_label", columns="platform_label", values="real_pct").fillna(0)
        fig_cov = px.imshow(
            pivot_cov,
            color_continuous_scale=[[0, "#FF4444"], [0.4, "#FFAA00"], [1, "#44BB44"]],
            labels={"x": "Plataforma", "y": "Ciudad", "color": "% con precio real"},
            text_auto=True,
            zmin=0, zmax=100,
        )
        fig_cov = plotly_layout(fig_cov, title="% de Registros con Precio Real Obtenido por Ciudad y Plataforma")
        st.plotly_chart(fig_cov, use_container_width=True)

        # Tabla detallada de estado
        with st.expander("Ver tabla detallada de estados por ciudad y plataforma"):
            status_breakdown = (
                prod_df.groupby(["city", "platform", "scraping_status"])
                .size()
                .reset_index(name="registros")
            )
            status_breakdown["ciudad"] = status_breakdown["city"].map(_CITY_LABELS).fillna(status_breakdown["city"])
            status_breakdown["plataforma"] = status_breakdown["platform"].map(PLATFORM_LABELS).fillna(status_breakdown["platform"])
            status_breakdown["estado"] = status_breakdown["scraping_status"].map(_STATUS_LABELS).fillna(status_breakdown["scraping_status"])
            st.dataframe(
                status_breakdown[["ciudad", "plataforma", "estado", "registros"]]
                .sort_values(["ciudad", "plataforma", "registros"], ascending=[True, True, False])
                .reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("---")

        # ── 3. Justificación por tipo de zona ────────────────────────────
        st.markdown("### Justificación Estratégica de la Selección")
        st.caption("Por qué se eligió cada tipo de zona y qué pregunta competitiva responde.")

        zone_cols = st.columns(3)
        for i, (zone_key, meta) in enumerate(_ZONE_META.items()):
            with zone_cols[i]:
                count = prod_df[prod_df["zone_type"] == zone_key]["address_id"].nunique() if "address_id" in prod_df.columns else "—"
                st.markdown(
                    f'<div class="insight-card">'
                    f'<div style="font-size:1.5rem;">{meta["icon"]}</div>'
                    f'<div style="color:#FF441A;font-weight:bold;margin:0.3rem 0;">{meta["title"]}</div>'
                    f'<div style="font-size:0.8rem;color:#555;margin-bottom:0.5rem;">{count} direcciones</div>'
                    f'<div style="font-size:0.85rem;">{meta["why"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Ciudades secundarias card (full width)
        sec_count = prod_df[prod_df["city"].isin(["puebla","tijuana","leon","merida","cancun"])]["address_id"].nunique() if "address_id" in prod_df.columns else 5
        st.markdown(
            f'<div class="insight-card">'
            f'<div style="font-size:1.5rem;">🌎</div>'
            f'<div style="color:#FF441A;font-weight:bold;margin:0.3rem 0;">Ciudades Secundarias</div>'
            f'<div style="font-size:0.8rem;color:#555;margin-bottom:0.5rem;">{sec_count} direcciones — Puebla, Tijuana, León, Mérida, Cancún</div>'
            f'<div style="font-size:0.85rem;">Mercados de expansión de mayor potencial para Rappi en 2025-2026. '
            f'Tienen penetración creciente de DiDi Food y UberEats pero cobertura limitada de Rappi. '
            f'Seleccionadas para medir el diferencial de fees en mercados fuera del core CDMX-GDL-MTY, '
            f'y detectar oportunidades donde competidores están consolidando posición antes que Rappi.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # ── 4. Tabla completa de direcciones ─────────────────────────────
        st.markdown("### Directorio Completo de Direcciones Analizadas")

        try:
            addr_df = load_addresses()
            addr_df["ciudad"] = addr_df["city"].map(_CITY_LABELS).fillna(addr_df["city"])
            addr_df["zona_tipo"] = addr_df["zone_type"].map(_ZONE_LABELS).fillna(addr_df["zone_type"])

            fa_col1, fa_col2 = st.columns(2)
            with fa_col1:
                city_filter = st.selectbox(
                    "Filtrar por ciudad",
                    ["Todas"] + sorted(addr_df["ciudad"].unique().tolist()),
                    key="addr_city_filter",
                )
            with fa_col2:
                zone_filter = st.selectbox(
                    "Filtrar por tipo de zona",
                    ["Todas"] + sorted(addr_df["zona_tipo"].unique().tolist()),
                    key="addr_zone_filter",
                )

            display_df = addr_df.copy()
            if city_filter != "Todas":
                display_df = display_df[display_df["ciudad"] == city_filter]
            if zone_filter != "Todas":
                display_df = display_df[display_df["zona_tipo"] == zone_filter]

            st.dataframe(
                display_df[["id", "address", "ciudad", "zone", "zona_tipo", "justification"]]
                .rename(columns={
                    "id": "ID", "address": "Dirección", "ciudad": "Ciudad",
                    "zone": "Zona", "zona_tipo": "Tipo", "justification": "Justificación estratégica",
                })
                .reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"{len(display_df)} de {len(addr_df)} direcciones mostradas.")
        except Exception as e:
            st.error(f"Error cargando direcciones: {e}")

# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown(
    f'<hr><p style="color:#999;font-size:0.75rem;text-align:center;">'
    f'Rappi Competitive Intelligence System | Modo: {scraping_mode.upper()} | '
    f'Datos: {str(timestamp)[:10]} | {success_records:,} registros analizados</p>',
    unsafe_allow_html=True,
)

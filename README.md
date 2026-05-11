# Rappi Competitive Intelligence System

Sistema automatizado de inteligencia competitiva para monitorear precios, fees y promociones de Rappi, Uber Eats y DiDi Food en México.

## Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        run_scraper.py                           │
│              (entry point — CLI con argparse)                    │
└──────────────┬──────────────────────────────────────────────────┘
               │
       ┌───────▼────────┐
       │  SCRAPING_MODE │
       └───┬────────┬───┘
           │        │
     mock  │        │ production
           │        │
    ┌──────▼──┐  ┌──▼──────────────────────────────────┐
    │  mock_  │  │  BaseScraper (retry, rate limit,     │
    │  data_  │  │  user-agent rotation, logging)       │
    │  gener  │  │                                      │
    │  ator   │  │  ┌──────────┐ ┌──────────┐ ┌──────┐ │
    └────┬────┘  │  │  Rappi   │ │UberEats  │ │ DiDi │ │
         │       │  │ Scraper  │ │ Scraper  │ │ Food │ │
         │       │  │(requests │ │(requests │ │(mock_│ │
         │       │  │direct API│ │direct API│ │fallbk│ │
         │       │  └────┬─────┘ └────┬─────┘ └──┬──┘ │
         │       └───────┼────────────┼───────────┼────┘
         │               │            │           │
         └───────────────▼────────────▼───────────▼
                    ┌─────────────────────────┐
                    │    data/raw/*.json       │
                    │    data/processed/*.csv  │
                    └──────────────┬──────────┘
                                   │
               ┌───────────────────▼──────────────────┐
               │           analysis/                   │
               │  comparator.py  │  insights_gen.py    │
               └──────┬──────────┴──────────┬──────────┘
                      │                     │
             ┌────────▼──────┐    ┌─────────▼────────┐
             │  dashboard/   │    │  reports/         │
             │  app.py       │    │  report_gen.py    │
             │  (Streamlit)  │    │  (HTML ejecutivo) │
             └───────────────┘    └──────────────────┘
```

## Setup

### Requisitos

- Python 3.11+
- pip
- (Para modo producción) Chrome/Chromium instalado vía Playwright

### Instalación

```bash
# 1. Clonar / descargar el proyecto
cd "Rappi Competitive Intelligence"

# 2. Crear entorno virtual (recomendado)
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. (Solo para modo producción) Instalar Chromium para Playwright
playwright install chromium

# 5. Configurar variables de entorno
copy .env.example .env
# Editar .env según necesidad
```

### Variables de entorno (.env)

| Variable | Valores | Default | Descripción |
|---|---|---|---|
| `SCRAPING_MODE` | `mock` / `production` | `mock` | Modo de operación |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` | `INFO` | Nivel de logging |
| `SCRAPERAPI_KEY` | string | — | API key de ScraperAPI (opcional) |

---

## Cómo ejecutar

### Modo desarrollo (datos mock)
```bash
python run_scraper.py --mode mock
# O con variable de entorno:
# En Windows: set SCRAPING_MODE=mock && python run_scraper.py
# En Mac/Linux: SCRAPING_MODE=mock python run_scraper.py
```

### Modo producción (datos reales)
```bash
python run_scraper.py --mode production
```

### Opciones adicionales
```bash
# Solo una ciudad
python run_scraper.py --cities cdmx

# Múltiples ciudades
python run_scraper.py --cities cdmx guadalajara monterrey

# Solo primeras N direcciones (testing rápido)
python run_scraper.py --addresses 5

# Scrape + generar informe HTML
python run_scraper.py --generate-report

# Combinaciones
python run_scraper.py --mode mock --cities cdmx --addresses 5 --generate-report
```

### Dashboard interactivo
```bash
streamlit run run_dashboard.py --server.port 8503
# Dashboard disponible en http://localhost:8503/
```

O directamente:
```bash
python run_dashboard.py
```

### Generar informe HTML
```bash
python run_scraper.py --generate-report
# El informe se guarda en reports/competitive_report_YYYYMMDD_HHMMSS.html
```

---

## Costos estimados

| Opción | Costo | Cuándo usar |
|---|---|---|
| **Playwright + stealth (actual)** | **$0/mes** | Desarrollo, scraping ocasional |
| **ScraperAPI** | ~$49/mes (100k requests) | Si Playwright empieza a ser bloqueado sistemáticamente (>30% de requests) |
| **Bright Data** | ~$500/mes | Scraping intensivo en producción (>1M requests/mes), múltiples países |
| **Oxylabs** | ~$300/mes | Alternativa a Bright Data, mejor soporte para México |

**Recomendación:** Iniciar con Playwright gratuito. Si el bloqueo supera 20%, migrar a ScraperAPI que tiene soporte nativo para los sitios principales de delivery.

---

## Direcciones seleccionadas y justificación estratégica

### CDMX — Zona Premium (5 direcciones)
| ID | Dirección | Justificación |
|---|---|---|
| cdmx_premium_01 | Presidente Masaryk 61, Polanco | Alta densidad usuarios premium, ticket máximo CDMX |
| cdmx_premium_02 | Álvaro Obregón 311, Roma Norte | Zona millennial, alta frecuencia de pedidos |
| cdmx_premium_03 | Presidente Carranza 198, Coyoacán | Zona familiar, mix amplio de categorías |
| cdmx_premium_04 | Insurgentes Sur 1602, Florida | Corredor empresarial, pico en almuerzo |
| cdmx_premium_05 | Molière 222, Polanco | Zona corporativa + residencial premium |

### CDMX — Zona Media (5 direcciones)
| ID | Dirección | Justificación |
|---|---|---|
| cdmx_media_01 | Eje Central 911, Centro Histórico | Alta densidad, price-sensitive |
| cdmx_media_02 | Calzada de Tlalpan 3386, Coapa | Zona familiar clase media |
| cdmx_media_03 | Insurgentes Norte 1235, GAM | Alta competencia entre plataformas |
| cdmx_media_04 | Ermita Iztapalapa 4624 | Sensibilidad máxima a delivery fees |
| cdmx_media_05 | División del Norte 2799, Del Valle | Zona residencial media |

### CDMX — Zona Periférica (5 direcciones)
Ecatepec, Atizapán, Naucalpan, Pedregal, Nezahualcóyotl — zonas de mayor oportunidad de expansión con mayor brecha competitiva vs DiDi Food.

### Guadalajara (5 direcciones)
Zapopan Vallarta (premium), Col. Americana (millennial), Zapopan Norte (corporativa), GDL Centro (tradicional), Tlaquepaque (periférica).

### Monterrey (5 direcciones)
San Pedro Garza García (ultra-premium), Centro MTY, zona universitaria (Garza Sada), Santa Catarina (industrial), zona media residencial.

### Ciudades secundarias (5 direcciones)
Puebla, Tijuana, León, Mérida, Cancún — representan el mercado de expansión de mayor potencial para Rappi en 2025-2026.

---

## Limitaciones conocidas

1. **Anti-scraping:** Rappi y Uber Eats implementan detección activa. En modo producción, esperar ~10-20% de requests bloqueadas en algunas ciudades.
2. **Rappi y Uber Eats:** Scrapers usan APIs internas descubiertas por network interception — `requests` puro, sin Playwright. No requieren renderizado JS.
3. **DiDi Food:** Web app auth-gated (cookie `ticket` en `.c.didi-food.com`). Las firmas anti-bot `wsgsig` son generadas por un SDK JS ofuscado irreproducible fuera del navegador. Siempre retorna `mock_fallback`.
4. **Cobertura geográfica:** Uber Eats solo tiene datos reales para CDMX (~15/30 direcciones). Otras ciudades retornan `mock_fallback` por falta de presencia de restaurantes en la API.
5. **Tiempo de ejecución:** Scraping completo de 30 direcciones × 3 plataformas ≈ 5-15 minutos en modo producción.
6. **Precios en tiempo real:** Los datos son un snapshot; precios pueden cambiar en minutos durante horas pico.
7. **Modo mock:** Los datos sintéticos son estadísticamente representativos pero no reemplazan datos reales para decisiones de pricing.

---

## Consideraciones éticas y legales

- **Robots.txt:** Los scrapers verifican y respetan `/robots.txt` de cada plataforma.
- **Rate limiting:** Delays aleatorios de 2-5 segundos entre requests para no sobrecargar servidores.
- **Finalidad:** Este sistema es para inteligencia competitiva interna, no para desestabilizar servicios.
- **Términos de Servicio:** Consultar con el equipo Legal de Rappi antes de implementar scraping sistemático en producción.
- **Datos personales:** El sistema no recolecta ningún dato personal de usuarios.

---

## Próximos pasos (con más tiempo)

1. **Automatización diaria:** Cron job con GitHub Actions para scraping automático cada 24h.
2. **Alertas:** Notificación en Slack cuando competidores bajen precios >10% en zonas estratégicas.
3. **Más competidores:** Integrar PedidosYa, iFood, Cornershop.
4. **Tendencias temporales:** Dashboard de series de tiempo para detectar patrones semanales/mensuales.
5. **Cobertura expandida:** 50+ ciudades secundarias en México.
6. **ML predictivo:** Modelo de predicción de movimientos de precios de competidores.
7. **API interna:** Exponer datos como API REST para consumo por otros equipos de Rappi.
8. **Capturas de pantalla:** Evidencia visual automática de promociones activas.

---

## Stack Tecnológico

| Componente | Tecnología | Justificación |
|---|---|---|
| Scraping Rappi | requests + BeautifulSoup | API interna descubierta vía network interception — SSG HTML + search API, sin JS rendering |
| Scraping Uber Eats | requests | APIs internas `getFeedV1` / `getStoreV1` con headers mínimos — más rápido y estable que Playwright |
| Scraping DiDi Food | mock_fallback | Auth-gated (cookie `ticket`) + firmas `wsgsig` irreproducibles. Documentado vía network interception |
| Network Interception | Playwright + playwright-stealth | Herramienta de investigación para descubrir endpoints reales de las plataformas |
| Procesamiento | pandas | Estándar de industria, excelente para análisis tabular |
| Dashboard | Streamlit + Plotly | Rapidez de desarrollo, resultados interactivos en horas |
| Reportes | HTML + matplotlib | Sin dependencias de servidor, fácil distribución |
| Config | python-dotenv | Separación limpia de config vs código |

---

## Mejor Stack para Producción Real

Esta sección documenta qué herramientas usar si se quisiera llevar este sistema a producción completa, plataforma por plataforma.

### Rappi — ya funciona, escalar con proxies residenciales

El scraper actual (requests + API interna) es el enfoque correcto. En producción a escala, el único riesgo es bloqueo por IP repetición.

**Solución recomendada: Bright Data Residential Proxies**
- Precio: ~$15 USD/GB (aprox. $150–300/mes para monitoreo diario de 30 direcciones × 8 productos)
- Por qué Bright Data: red de 72M+ IPs residenciales reales, rotación automática, geo-targeting por ciudad (CDMX, GDL, MTY)
- Integración: solo cambiar el parámetro `proxies=` en `requests.get()` — el scraper no cambia
- Alternativa más barata: **Oxylabs** ~$10/GB, menor red pero suficiente para México

### Uber Eats — extender cobertura a todas las ciudades

El problema actual: la API interna (`getFeedV1`) solo devuelve restaurantes dentro de un radio geográfico real. Fuera de CDMX no encuentra tiendas porque la IP no está geolocalizada.

**Solución recomendada: Bright Data Residential Proxies con geo-targeting por ciudad**
- Mismo precio que arriba (~$15/GB), pero con IPs específicas de Guadalajara, Monterrey, Puebla, etc.
- La API de Uber Eats "ve" una IP de GDL y devuelve restaurantes de GDL — resuelve el problema de cobertura sin cambiar nada del scraper

### DiDi Food — el más difícil, requiere enfoque mobile

DiDi es el reto real. El problema no es el scraping en sí, sino que: (1) la app requiere login con cookie `ticket` efímero, (2) las firmas `wsgsig` se generan en un SDK JS ofuscado que cambia con cada versión, y (3) no existe interfaz web pública.

**Opción A — Automatización mobile con Appium (recomendada para uso interno)**
- **Appium** + emulador Android: automatiza la app móvil real de DiDi Food
- **mitmproxy** (gratuito): intercepta el tráfico HTTPS del emulador para capturar las respuestas de la API
- Precio: $0 (open source) + servidor cloud para el emulador (~$50–80/mes en GCP/AWS con instancia e2-standard-2)
- Limitación: requiere gestionar actualizaciones de la app y renovar el login periódicamente

**Opción B — Bright Data Scraping Browser (recomendada si DiDi es prioritario)**
- Browser gestionado en la nube con bypass de anti-bot automático
- Precio: ~$8.4 USD/GB (aprox. $200–400/mes para cobertura completa)
- Bright Data gestiona las firmas anti-bot, fingerprinting de dispositivo y rotación de sesiones — solo se escribe el código de extracción
- Integración: Playwright apunta al endpoint de Bright Data en vez del Chromium local — 3 líneas de cambio en el código

**Opción C — Zyte API**
- Bypass automático de anti-bot, soporte para apps de delivery
- Precio: $0.10 USD por 1,000 requests (~$20–50/mes para volumen moderado)

### Stack completo recomendado para producción

| Plataforma | Herramienta | Precio estimado/mes |
|---|---|---|
| **Rappi** | requests actuales + Bright Data Residential | $150–300 USD |
| **Uber Eats** | requests actuales + Bright Data con geo-targeting | (incluido arriba) |
| **DiDi Food** | Appium + mitmproxy + emulador GCP | $50–80 USD |
| **Orquestación** | GitHub Actions (cron diario) | $0–4 USD |
| **Almacenamiento** | Google Cloud Storage o Supabase | $5–20 USD |
| **Total estimado** | | **$205–404 USD/mes** |

Para un equipo de Competitive Intelligence que necesita datos frescos diariamente de 3 plataformas en 8 ciudades, este costo representa menos de 1 hora de trabajo de un analista — ROI claro si el sistema alimenta decisiones de pricing.

### ¿Por qué no usar servicios "todo en uno" como ScraperAPI o Apify?

- **ScraperAPI** (~$49/mes): funciona bien para sitios simples, pero no tiene bypass nativo para `wsgsig` de DiDi ni para los headers específicos de Uber Eats
- **Apify** (~$49–499/mes): plataforma excelente para scraping general, pero no tiene actores mantenidos para estas plataformas en México
- **Conclusión**: es más eficiente mantener los scrapers propios (que ya conocen las APIs internas) y solo delegar el problema de IP a Bright Data

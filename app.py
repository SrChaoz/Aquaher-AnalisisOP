"""Local Streamlit interface for the supplied Aquaher RO analysis."""

from __future__ import annotations

import math

import plotly.express as px
import streamlit as st

from ro_model import Config, analyze, calculate_measurement, demo_rows, load_excel, simulate_temperature, to_excel


st.set_page_config(page_title="Aquaher · Análisis de ósmosis inversa", layout="wide")

st.markdown("""
<style>
  :root { --ink:#103848; --sea:#067c91; --mist:#eaf5f6; }
  .block-container { max-width: 1260px; padding-top: 2.2rem; }
  h1,h2,h3 { color:var(--ink); letter-spacing:-.025em; }
  h1 { font-size: clamp(2.1rem, 4vw, 3.15rem); }
  [data-testid="stMetric"] { background:#eef7f7; border:1px solid #d1e8e8; border-radius:14px; padding:16px 18px; }
  [data-testid="stMetricLabel"] { color:#315767; }
  div.stButton > button, div.stDownloadButton > button { min-height:44px; }
  .muted { color:#426271; max-width:72ch; line-height:1.55; }
</style>
""", unsafe_allow_html=True)

st.caption("AQUAHER  /  ANÁLISIS OPERATIVO")
st.title("Análisis de ósmosis inversa")
st.markdown('<p class="muted">Calcula indicadores hidráulicos de una medición o analiza una hoja operativa completa. '
            'Las señales de fouling son exploratorias y requieren revisión técnica antes de tomar decisiones.</p>',
            unsafe_allow_html=True)

with st.sidebar:
    st.header("Parámetros del modelo")
    st.caption("Valores iniciales del código de investigación entregado.")
    membranes = st.number_input("Número de membranas", min_value=1, value=96, step=1)
    area = st.number_input("Área por membrana (m²)", min_value=0.1, value=37.2, step=0.1)
    reference_temp = st.number_input("Temperatura de referencia (°C)", min_value=-5.0,
                                     max_value=60.0, value=25.0, step=0.5)
    permeate_pressure = st.number_input("Presión de permeado (psi)", value=0.0, step=0.5)
    with st.expander("Configuración de ciclos y alerta"):
        max_gap = st.number_input("Nueva operación tras pausa mayor a (h)",
                                  min_value=0.1, value=4.0, step=0.5)
        quantile_pct = st.number_input("Percentil basal para la alerta (%)",
                                       min_value=1, max_value=49, value=5, step=1)
        band = st.number_input("Banda del mapa diagnóstico (%)", min_value=0.1,
                               value=5.0, step=0.5)
    st.info("Confirma que las presiones de tu archivo estén en psi y los TDS en mg/L.")

config = Config(membranes=int(membranes), element_area_m2=area,
                reference_temp_c=reference_temp, permeate_pressure_psi=permeate_pressure,
                max_gap_h=max_gap, basal_quantile=quantile_pct / 100,
                diagnostic_band_pct=band)

quick_tab, workbook_tab, method_tab = st.tabs(["Cálculo rápido", "Análisis de archivo", "Método y límites"])

with quick_tab:
    st.subheader("Una medición")
    st.write("Introduce los cinco valores necesarios para estimar flujo, presión neta y permeabilidad efectiva.")
    st.caption("Los valores que aparecen al abrir la página son solo un ejemplo de uso.")
    with st.form("quick_calculation"):
        col1, col2, col3 = st.columns(3)
        with col1:
            qp = st.number_input("Caudal de permeado Qp (L/s)", min_value=0.01, value=10.0, step=0.1)
        with col2:
            p_high = st.number_input("Presión alta (psi)", min_value=0.0, value=200.0, step=1.0)
        with col3:
            p_reject = st.number_input("Presión de rechazo (psi)", min_value=0.0, value=180.0, step=1.0)
        tds1, tds2 = st.columns(2)
        with tds1:
            tds_feed = st.number_input("TDS de alimentación (mg/L)", min_value=0.0, value=1000.0, step=10.0)
        with tds2:
            tds_product = st.number_input("TDS de producto (mg/L)", min_value=0.0, value=50.0, step=10.0)
        run_quick = st.form_submit_button("Calcular", type="primary")
    if run_quick:
        values = calculate_measurement(qp, p_high, p_reject, tds_feed, tds_product, config)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Flujo Jw", f"{values['Jw']:.2f} L/(m²·h)")
        m2.metric("Diferencia osmótica", f"{values['Delta_pi']:.2f} psi")
        m3.metric("Presión neta NDP", f"{values['NDP']:.2f} psi")
        m4.metric("Permeabilidad Aeff", f"{values['Aeff']:.4f} L/(m²·h·psi)" if math.isfinite(values["Aeff"]) else "No calculable")
        if values["NDP"] <= 0:
            st.error("La NDP calculada no es positiva. Revisa presiones, TDS y unidades.")
        else:
            st.caption("Una sola medición no permite diagnosticar fouling: se necesita la evolución de un ciclo.")

with workbook_tab:
    st.subheader("Analiza una hoja operativa")
    st.write("Carga un .xlsx con la hoja **DATA-OSMOSIS**. Los registros empiezan en la fila 8; la app usa las columnas A, D y L a V según los encabezados de la hoja.")
    mode = st.radio("Origen de los datos", ["Cargar Excel", "Probar demostración"], horizontal=True)
    uploaded = (st.file_uploader("Archivo Excel de operación", type=["xlsx"],
                                help="No se envía a un servidor externo cuando ejecutas la app localmente.")
                if mode == "Cargar Excel" else None)
    if mode == "Cargar Excel" and uploaded is None:
        st.info("Cuando tengas el Excel de planta, cárgalo aquí para ver ciclos, alertas y simulaciones.")
    else:
        if mode == "Probar demostración":
            st.warning("DATOS SINTÉTICOS · Solo sirven para explorar la aplicación; no describen la planta Aquaher.")
        try:
            data = demo_rows() if mode == "Probar demostración" else load_excel(uploaded.getvalue())
            result = analyze(data, config)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            st.error(f"No se pudo analizar el archivo: {exc}")
            st.stop()

        rows_loaded = len(data)
        a, b, c, d = st.columns(4)
        a.metric("Registros leídos", f"{rows_loaded:,}")
        b.metric("Registros operativos", f"{len(result.operational):,}")
        c.metric("Ciclos", len(result.operational["Ciclo"].unique()))
        d.metric("Ciclos con alerta", len(result.first_alerts))
        if mode == "Cargar Excel":
            st.info("Se leyó TDS de producto desde S y no desde R (R es dureza). Por eso los indicadores pueden diferir del cuaderno entregado.")
        if result.excluded_ndp:
            st.warning(f"{result.excluded_ndp} registros tuvieron NDP ≤ 0; no se calculó Aeff en ellos.")
        if result.baseline.empty:
            st.warning("No hay ciclos con tres mediciones físicas válidas para calibrar la alerta basal.")

        sim = temp_summary = None
        overview, cycle_tab, alert_tab, simulation_tab = st.tabs(
            ["Resumen", "Detalle del ciclo", "Alerta exploratoria", "Temperatura"])
        with overview:
            st.caption(f"Banda diagnóstica de ±{band:g}%: recurso visual exploratorio, no límite físico de Aquaher.")
            if result.cycles.empty:
                st.warning("Ningún ciclo tiene presión neta y permeabilidad válidas para el diagnóstico.")
            else:
                left, right = st.columns([1.2, 1])
                with left:
                    fig = px.scatter(result.cycles, x="Delta_NDP_pct", y="Delta_Aeff_pct",
                                     text=result.cycles["Ciclo"].map(lambda x: f"C{x}"),
                                     hover_data=["Diagnostico", "n"],
                                     labels={"Delta_NDP_pct": "Cambio de NDP (%)",
                                             "Delta_Aeff_pct": "Cambio de Aeff (%)"},
                                     title="Operación y permeabilidad por ciclo")
                    for threshold in (-band, 0, band):
                        fig.add_vline(x=threshold, line_dash="dash" if threshold else "solid",
                                      line_color="#8aa4ad")
                        fig.add_hline(y=threshold, line_dash="dash" if threshold else "solid",
                                      line_color="#8aa4ad")
                    fig.update_traces(marker=dict(size=11, color="#087e91"), textposition="top center")
                    st.plotly_chart(fig, width="stretch")
                with right:
                    st.dataframe(result.cycles[["Ciclo", "n", "Duracion_h", "Delta_Qp_pct",
                                               "Delta_NDP_pct", "Delta_Aeff_pct", "Diagnostico"]].round(3),
                                 hide_index=True, width="stretch")

        valid_cycles = result.cycles["Ciclo"].astype(int).tolist() if not result.cycles.empty else []
        selected_cycle = None
        with cycle_tab:
            if valid_cycles:
                selected_cycle = st.selectbox("Ciclo", valid_cycles,
                                              format_func=lambda value: f"Ciclo {value}")
                points = result.operational.loc[result.operational["Ciclo"] == selected_cycle].copy()
                points["Qp_rel"] = 100 * points["Qp"] / points["Qp"].iloc[0]
                points["NDP_rel"] = 100 * points["NDP"] / points["NDP"].iloc[0]
                points["Aeff_rel"] = 100 * points["Aeff"] / points["Aeff"].iloc[0]
                left, right = st.columns(2)
                with left:
                    fig = px.line(points, x="tau_h", y=["Qp_rel", "NDP_rel", "Aeff_rel"], markers=True,
                                  labels={"tau_h": "Horas desde el inicio", "value": "% del valor inicial", "variable": "Indicador",
                                          "Qp_rel": "Qp", "NDP_rel": "NDP", "Aeff_rel": "Aeff"},
                                  title="Cambios relativos dentro del ciclo")
                    fig.add_hline(y=100, line_dash="dash", line_color="#8aa4ad")
                    st.plotly_chart(fig, width="stretch")
                with right:
                    fig = px.line(points, x="tau_h", y="AN", markers=True,
                                  labels={"tau_h": "Horas desde el inicio", "AN": "Aeff / Aref"},
                                  title="Permeabilidad normalizada")
                    fig.add_hline(y=1, line_dash="dash", line_color="#8aa4ad")
                    st.plotly_chart(fig, width="stretch")
                st.dataframe(points[["FechaHora", "Qp", "NDP", "Aeff", "AN", "TDS_alim", "TDS_prod"]].round(4),
                             hide_index=True, width="stretch")
            else:
                st.info("No hay ciclos con indicadores físicos válidos.")

        with alert_tab:
            st.write("El límite se calcula con el percentil basal de las primeras tres mediciones válidas por ciclo. "
                     "Desde la cuarta medición se piden dos candidatos consecutivos para mostrar una alerta.")
            if result.baseline.empty:
                st.info("La alerta no puede evaluarse con este archivo.")
            else:
                a, b = st.columns(2)
                a.metric("Límite Aeff normalizada", f"{result.limit_a:.4f}")
                b.metric("Límite NDP normalizada", f"{result.limit_ndp:.4f}")
                if result.first_alerts.empty:
                    st.success("No hubo ciclos con alerta bajo esta calibración.")
                else:
                    st.dataframe(result.first_alerts.round(4), hide_index=True, width="stretch")
                if selected_cycle is not None and not result.monitoring.empty:
                    track = result.monitoring.loc[result.monitoring["Ciclo"] == selected_cycle]
                    if not track.empty:
                        fig = px.line(track, x="tau_h", y="AN_alerta", markers=True,
                                      labels={"tau_h": "Horas desde el inicio", "AN_alerta": "Aeff / Aref"},
                                      title=f"Seguimiento del ciclo {selected_cycle}")
                        fig.add_hline(y=result.limit_a, line_dash="dash", line_color="#b9533f")
                        st.plotly_chart(fig, width="stretch")
                        st.dataframe(track[["FechaHora", "AN_alerta", "NDP_N_alerta", "Estado"]].round(4),
                                     hide_index=True, width="stretch")

        with simulation_tab:
            st.write("Contrafactual: cambia solo la temperatura; conserva las presiones, TDS y estado de la membrana registrados.")
            if selected_cycle is None:
                st.info("Se necesita un ciclo válido para simular.")
            else:
                target_temp = st.slider("Temperatura adicional (°C)", min_value=5, max_value=45,
                                        value=30, step=1)
                try:
                    sim, temp_summary = simulate_temperature(result.operational, selected_cycle,
                                                              [target_temp], config)
                    fig = px.line(sim, x="tau_h", y="Qp_sim_Ls", color="Temperatura_C",
                                  markers=True, color_discrete_sequence=["#087e91", "#c6683f"],
                                  labels={"tau_h": "Horas desde el inicio", "Qp_sim_Ls": "Qp simulado (L/s)",
                                          "Temperatura_C": "Temperatura (°C)"},
                                  title="Caudal estimado por temperatura")
                    st.plotly_chart(fig, width="stretch")
                    st.dataframe(temp_summary.round(3), hide_index=True, width="stretch")
                except ValueError as exc:
                    st.warning(str(exc))
                    sim = temp_summary = None

        st.download_button("Descargar resultados (.xlsx)",
                           to_excel(result, sim, temp_summary),
                           file_name=("DEMO_sintetica_Aquaher_RO.xlsx" if mode == "Probar demostración"
                                      else "Resultados_Aquaher_RO.xlsx"),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary")

with method_tab:
    st.subheader("Qué calcula esta versión")
    st.markdown("""
1. **Ciclos:** registros con Qp positivo; una pausa mayor a 4 horas inicia otro ciclo (ajustable).
2. **Flujo de agua:** `Jw = Qp × 3600 / (número de membranas × área por membrana)`.
3. **Presión osmótica:** aproximación de Van ’t Hoff con los TDS expresados como NaCl equivalente.
4. **Presión neta:** `NDP = (P_alta + P_rechazo)/2 − P_permeado − (π_alim − π_prod)`.
5. **Permeabilidad efectiva:** `Aeff = Jw/NDP` cuando NDP es positiva.
6. **Alerta exploratoria:** percentil basal de Aeff y NDP normalizadas; requiere dos candidatos seguidos después de tres mediciones de referencia.
7. **Temperatura:** corrección TCF y ajuste de NDP por presión osmótica, según el cuaderno recibido.
""")
    st.warning("La hoja de abril identifica R como dureza y S como TDS de producto. El cuaderno Python y el código R leen esas columnas desplazadas; esta app sigue los encabezados reales. "
               "La regresión de la presentación no se incorpora porque no figura implementada en el cuaderno reproducible y no se han validado sus unidades ni desempeño.")
    st.caption("Fuente técnica: cuaderno Python y código R de la entrega UTM–Aquaher, septiembre de 2026.")

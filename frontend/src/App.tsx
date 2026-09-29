import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, ArrowDownToLine, FileSpreadsheet, Info, Menu, UploadCloud, X } from 'lucide-react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { analyzeFile, apiJson, exportFile, simulate } from './api'
import type { Analysis, Config, RecordRow, Simulation } from './types'

const INITIAL_CONFIG: Config = {
  membranes: 96, element_area_m2: 37.2, reference_temp_c: 25,
  permeate_pressure_psi: 0, max_gap_h: 4, basal_quantile: 0.05,
  diagnostic_band_pct: 5,
}
const TABS = ['Resumen', 'Ciclos', 'Alertas', 'Temperatura', 'Cálculo manual', 'Método'] as const
type Tab = typeof TABS[number]
const n = (row: RecordRow, key: string): number => Number(row[key])
const fmt = (value: unknown, digits = 2): string => {
  const number = Number(value)
  return value === null || value === undefined || !Number.isFinite(number)
    ? '—' : new Intl.NumberFormat('es-EC', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(number)
}
const date = (value: unknown): string => typeof value === 'string' ? new Date(value).toLocaleString('es-EC', { dateStyle: 'short', timeStyle: 'short' }) : '—'

function Notice({ children, tone = 'info' }: { children: React.ReactNode; tone?: 'info' | 'error' | 'success' }) {
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>
}

function NumberField({ label, value, onChange, min, max, step = 'any', hint }: {
  label: string; value: number; onChange: (value: number) => void; min?: number; max?: number; step?: string; hint?: string
}) {
  return <label className="field"><span>{label}</span><input type="number" value={value} min={min} max={max} step={step} onChange={event => onChange(Number(event.target.value))} />{hint && <small>{hint}</small>}</label>
}

function Card({ title, subtitle, children, action, className = '' }: {
  title: string; subtitle?: string; children: React.ReactNode; action?: React.ReactNode; className?: string
}) {
  return <section className={`card ${className}`}><div className="card-heading"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>{action}</div>{children}</section>
}

function Metric({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>
}

function EmptyAnalysis() {
  return <div className="empty-state"><div className="empty-icon"><FileSpreadsheet size={24} strokeWidth={1.7} /></div><h2>Sin archivo analizado</h2><p>Selecciona el registro operativo de la planta para consultar indicadores, ciclos y alertas.</p><ol><li>Prepara un archivo Excel con la hoja <strong>DATA-OSMOSIS</strong>.</li><li>Comprueba que los datos comiencen en la fila 8.</li><li>Carga el archivo y selecciona <strong>Analizar archivo</strong>.</li></ol></div>
}

function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [tab, setTab] = useState<Tab>('Resumen')
  const [menuOpen, setMenuOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [config, setConfig] = useState<Config>(INITIAL_CONFIG)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cycle, setCycle] = useState(1)
  const [temperature, setTemperature] = useState(30)
  const [simulation, setSimulation] = useState<Simulation | null>(null)
  const [simBusy, setSimBusy] = useState(false)
  const [simError, setSimError] = useState('')
  const [exportBusy, setExportBusy] = useState(false)
  const [manual, setManual] = useState({ qp_l_s: 20, p_high_psi: 150, p_reject_psi: 100, tds_feed_mg_l: 517, tds_product_mg_l: 49.8 })
  const [manualResult, setManualResult] = useState<Record<string, number | null> | null>(null)
  const [manualBusy, setManualBusy] = useState(false)
  const [manualError, setManualError] = useState('')

  useEffect(() => {
    setAnalysis(null)
    setSimulation(null)
    setManualResult(null)
  }, [config])

  const cycleRows = useMemo(() => analysis?.operational.filter(row => n(row, 'Ciclo') === cycle) ?? [], [analysis, cycle])
  const monitorRows = useMemo(() => analysis?.monitoring.filter(row => n(row, 'Ciclo') === cycle) ?? [], [analysis, cycle])
  const activeCycle = analysis?.cycles.find(row => n(row, 'Ciclo') === cycle)

  function chooseFile(selected: File | undefined) {
    if (!selected) return
    setError('')
    if (!selected.name.toLowerCase().endsWith('.xlsx')) { setError('Selecciona un archivo Excel .xlsx.'); return }
    if (selected.size > 4_000_000) { setError('El archivo supera el límite de 4 MB.'); return }
    setFile(selected)
    setAnalysis(null)
    setSimulation(null)
  }

  async function runAnalysis() {
    if (!file) return
    setBusy(true); setError(''); setAnalysis(null); setSimulation(null)
    try {
      const result = await analyzeFile(file, config)
      setAnalysis(result)
      setCycle(Number(result.cycles[0]?.Ciclo ?? 1))
      setTab('Resumen')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo analizar el archivo.') }
    finally { setBusy(false) }
  }

  useEffect(() => {
    if (!analysis || tab !== 'Temperatura') return
    let active = true
    setSimBusy(true); setSimError(''); setSimulation(null)
    simulate(analysis.operational, cycle, temperature, config)
      .then(result => { if (active) setSimulation(result) })
      .catch(cause => { if (active) setSimError(cause instanceof Error ? cause.message : 'No se pudo simular la temperatura.') })
      .finally(() => { if (active) setSimBusy(false) })
    return () => { active = false }
  }, [analysis, cycle, temperature, config, tab])

  async function download() {
    if (!file) return
    setExportBusy(true); setError('')
    try { await exportFile(file, config, cycle, temperature) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo exportar.') }
    finally { setExportBusy(false) }
  }

  async function calculate() {
    setManualBusy(true); setManualError(''); setManualResult(null)
    try {
      const result = await apiJson<Record<string, number | null>>('calculate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...manual, config }) })
      setManualResult(result)
    } catch (cause) { setManualError(cause instanceof Error ? cause.message : 'No se pudo calcular.') }
    finally { setManualBusy(false) }
  }

  const header = <header className="site-header"><div className="header-inner"><div className="brand"><div className="brand-mark" aria-hidden="true"><Activity size={21} /></div><div><strong>AQUAHER</strong><span>ANÁLISIS OPERATIVO</span></div></div><div className="header-right"><span className="header-tag">Sistema de ósmosis inversa</span><button className="menu-toggle" aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'} aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button></div></div></header>

  return <>{header}<main className="app-shell">
    <div className="page-heading"><div><p className="eyebrow">PLANTA DE TRATAMIENTO</p><h1>Análisis de ósmosis inversa</h1><p>Evaluación de registros operativos y desempeño del sistema.</p></div>{analysis && <button className="button button-secondary download-top" onClick={download} disabled={exportBusy}><ArrowDownToLine size={17} />{exportBusy ? 'Preparando…' : 'Exportar resultados'}</button>}</div>
    <nav className={`tabs ${menuOpen ? 'tabs-open' : ''}`} aria-label="Secciones de la aplicación">{TABS.map(item => <button key={item} className={tab === item ? 'tab active' : 'tab'} onClick={() => { setTab(item); setMenuOpen(false) }} aria-current={tab === item ? 'page' : undefined}>{item}</button>)}</nav>

    {tab === 'Resumen' && <div className="section-stack">
      <Card title="Archivo de registros" subtitle="Carga un libro Excel con el formato operativo de la planta." className="upload-card">
        <div className="upload-layout"><div className="upload-input" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]) }}><input ref={inputRef} type="file" accept=".xlsx" className="sr-only" onChange={event => chooseFile(event.target.files?.[0])} /><UploadCloud size={24} strokeWidth={1.6} /><div><strong>{file ? file.name : 'Seleccionar archivo Excel'}</strong><span>{file ? `${fmt(file.size / 1024, 0)} KB · listo para analizar` : 'Formato .xlsx · tamaño máximo 4 MB'}</span></div><button className="button button-secondary" onClick={() => inputRef.current?.click()}>Examinar</button></div><div className="upload-actions"><button className="button button-primary" onClick={runAnalysis} disabled={!file || busy}>{busy ? 'Analizando…' : 'Analizar archivo'}</button><p>El archivo se procesa para generar el análisis y no se conserva en la aplicación.</p></div></div>
        <details className="settings"><summary>Parámetros del modelo</summary><div className="form-grid settings-grid"><NumberField label="Membranas" value={config.membranes} min={1} step="1" onChange={value => setConfig({ ...config, membranes: value })} /><NumberField label="Área por elemento (m²)" value={config.element_area_m2} min={0.1} onChange={value => setConfig({ ...config, element_area_m2: value })} /><NumberField label="Temperatura de referencia (°C)" value={config.reference_temp_c} min={-5} max={60} onChange={value => setConfig({ ...config, reference_temp_c: value })} /><NumberField label="Presión de permeado (psi)" value={config.permeate_pressure_psi} min={0} onChange={value => setConfig({ ...config, permeate_pressure_psi: value })} /><NumberField label="Separación entre ciclos (h)" value={config.max_gap_h} min={0.1} onChange={value => setConfig({ ...config, max_gap_h: value })} /><NumberField label="Percentil basal" value={config.basal_quantile} min={0.01} max={0.49} onChange={value => setConfig({ ...config, basal_quantile: value })} /><NumberField label="Banda diagnóstica (%)" value={config.diagnostic_band_pct} min={0.1} max={50} onChange={value => setConfig({ ...config, diagnostic_band_pct: value })} /></div></details>
      </Card>
      {error && <Notice tone="error">{error}</Notice>}
      {busy && <div className="loading-card"><div className="spinner" /> Procesando registros y calculando indicadores…</div>}
      {!analysis && !busy && <EmptyAnalysis />}
      {analysis && <><div className="metric-grid"><Metric label="Registros leídos" value={analysis.summary.read_rows} /><Metric label="Registros operativos" value={analysis.summary.operational_rows} /><Metric label="Ciclos analizados" value={analysis.summary.cycles} /><Metric label="Ciclos con alerta" value={analysis.summary.alert_cycles} /></div>
        <div className="two-columns"><Card title="Variación por ciclo" subtitle="Cambio porcentual entre el inicio y el final de cada ciclo."><div className="chart" role="img" aria-label="Gráfico de variación porcentual de permeabilidad efectiva y presión neta por ciclo"><ResponsiveContainer width="100%" height="100%"><ScatterChart margin={{ top: 14, right: 16, bottom: 8, left: -12 }}><CartesianGrid stroke="#e7ecea" /><XAxis type="number" dataKey="Delta_NDP_pct" name="Cambio NDP" unit="%" tick={{ fontSize: 11 }} /><YAxis type="number" dataKey="Delta_Aeff_pct" name="Cambio Aeff" unit="%" tick={{ fontSize: 11 }} /><Tooltip cursor={{ strokeDasharray: '3 3' }} formatter={(value: number, name: string) => [fmt(value), name]} /><ReferenceLine x={0} stroke="#9caeaa" /><ReferenceLine y={0} stroke="#9caeaa" /><Scatter name="Ciclos" data={analysis.cycles} fill="#08796c" /></ScatterChart></ResponsiveContainer></div><p className="caption">Cada punto representa un ciclo. La clasificación detallada aparece en la sección Ciclos.</p></Card>
        <Card title="Datos del análisis" subtitle="Periodo y condiciones de cálculo."><dl className="detail-list"><div><dt>Periodo registrado</dt><dd>{analysis.summary.first_date} al {analysis.summary.last_date}</dd></div><div><dt>Membranas</dt><dd>{config.membranes}</dd></div><div><dt>Área total</dt><dd>{fmt(config.membranes * config.element_area_m2, 1)} m²</dd></div><div><dt>Temperatura de referencia</dt><dd>{fmt(config.reference_temp_c, 0)} °C</dd></div><div><dt>NDP no positiva</dt><dd>{analysis.summary.invalid_ndp} registros</dd></div></dl><Notice>Las alertas son indicadores exploratorios calculados a partir del archivo cargado. Verifica las unidades y los sensores antes de usarlas en decisiones operativas.</Notice></Card></div>
        <div className="mobile-export"><button className="button button-secondary" onClick={download} disabled={exportBusy}><ArrowDownToLine size={17} />{exportBusy ? 'Preparando…' : 'Exportar resultados'}</button></div>
      </>}
    </div>}

    {tab === 'Ciclos' && <div className="section-stack">{!analysis ? <EmptyAnalysis /> : <><div className="section-toolbar"><div><h2>Ciclos operativos</h2><p>Los ciclos se separan cuando transcurren más de {fmt(config.max_gap_h, 1)} horas entre mediciones.</p></div><CycleSelect cycles={analysis.cycles} value={cycle} onChange={setCycle} /></div><div className="metric-grid metric-grid-three"><Metric label="Mediciones del ciclo" value={activeCycle?.n as number ?? 0} /><Metric label="Duración" value={`${fmt(activeCycle?.Duracion_h)} h`} /><Metric label="Cambio de permeabilidad" value={`${fmt(activeCycle?.Delta_Aeff_pct)} %`} /></div><Card title={`Detalle del ciclo ${cycle}`} subtitle={activeCycle ? `${date(activeCycle.Inicio)} · ${date(activeCycle.Fin)}` : undefined}><div className="status-line"><span className="label">Clasificación</span><span className="status-pill">{String(activeCycle?.Diagnostico ?? 'Sin datos suficientes')}</span></div><div className="chart" role="img" aria-label="Tendencia porcentual del caudal de permeado, presión neta y permeabilidad efectiva"><ResponsiveContainer width="100%" height="100%"><LineChart data={normalizedCycle(cycleRows)} margin={{ top: 10, right: 15, bottom: 6, left: -12 }}><CartesianGrid stroke="#e7ecea" /><XAxis dataKey="tau_h" tick={{ fontSize: 11 }} unit="h" /><YAxis tick={{ fontSize: 11 }} unit="%" /><Tooltip formatter={(value: number) => `${fmt(value)} %`} /><ReferenceLine y={100} stroke="#9caeaa" strokeDasharray="3 3" /><Legend /><Line type="monotone" dataKey="Qp" name="Qp" stroke="#08796c" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="NDP" name="NDP" stroke="#d28a39" dot={false} strokeWidth={2} /><Line type="monotone" dataKey="Aeff" name="Aeff" stroke="#536b85" dot={false} strokeWidth={2} /></LineChart></ResponsiveContainer></div><p className="caption">Series normalizadas a 100 % en la primera medición. Los valores con sus unidades están en la tabla.</p><DataTable rows={cycleRows} columns={[['FechaHora', 'Fecha y hora', date], ['Qp', 'Qp (L/s)'], ['NDP', 'NDP (psi)'], ['Aeff', 'Aeff'], ['AN', 'A normalizada']]} /></Card><Card title="Resumen de todos los ciclos" subtitle="Selecciona un ciclo para consultar sus mediciones."><DataTable rows={analysis.cycles} columns={[['Ciclo', 'Ciclo'], ['n', 'Mediciones'], ['Duracion_h', 'Duración (h)'], ['Delta_Qp_pct', 'Δ Qp (%)'], ['Delta_NDP_pct', 'Δ NDP (%)'], ['Delta_Aeff_pct', 'Δ Aeff (%)'], ['Diagnostico', 'Clasificación']]} onRowClick={row => setCycle(n(row, 'Ciclo'))} /></Card></>}</div>}

    {tab === 'Alertas' && <div className="section-stack">{!analysis ? <EmptyAnalysis /> : <><div className="section-toolbar"><div><h2>Seguimiento de alertas</h2><p>Señales exploratorias por ciclo basadas en la variación basal de los registros.</p></div><CycleSelect cycles={analysis.cycles} value={cycle} onChange={setCycle} /></div><div className="metric-grid metric-grid-three"><Metric label="Límite A normalizada" value={fmt(analysis.summary.limit_a, 3)} /><Metric label="Límite NDP normalizada" value={fmt(analysis.summary.limit_ndp, 3)} /><Metric label="Ciclos con alerta" value={analysis.summary.alert_cycles} /></div><Notice>Una alerta requiere dos mediciones consecutivas con permeabilidad normalizada bajo su límite y presión neta normalizada igual o superior al suyo, después de las tres mediciones basales.</Notice><Card title="Primera alerta por ciclo" subtitle="Momento de la primera señal persistente registrada en cada ciclo.">{analysis.first_alerts.length ? <DataTable rows={analysis.first_alerts} columns={[['Ciclo', 'Ciclo'], ['FechaHora_alerta', 'Fecha y hora', date], ['Hora_alerta_desde_inicio_h', 'Horas desde inicio'], ['AN_en_alerta', 'A normalizada'], ['NDP_N_en_alerta', 'NDP normalizada']]} /> : <p className="quiet-empty">No se detectaron alertas con estos parámetros.</p>}</Card><Card title={`Seguimiento del ciclo ${cycle}`} subtitle="Estados calculados para las mediciones evaluables.">{monitorRows.length ? <DataTable rows={monitorRows} columns={[['FechaHora', 'Fecha y hora', date], ['tau_h', 'Hora del ciclo'], ['AN_alerta', 'A normalizada'], ['NDP_N_alerta', 'NDP normalizada'], ['Estado', 'Estado']]} /> : <p className="quiet-empty">Este ciclo no tiene suficientes mediciones válidas para evaluar alertas.</p>}</Card></>}</div>}

    {tab === 'Temperatura' && <div className="section-stack">{!analysis ? <EmptyAnalysis /> : <><div className="section-toolbar"><div><h2>Simulación de temperatura</h2><p>Estimación del caudal para un ciclo, manteniendo las demás condiciones observadas.</p></div><div className="toolbar-controls"><CycleSelect cycles={analysis.cycles} value={cycle} onChange={setCycle} /><NumberField label="Temperatura simulada (°C)" value={temperature} min={5} max={45} onChange={setTemperature} /></div></div>{simError && <Notice tone="error">{simError}</Notice>}{simBusy && <div className="loading-card"><div className="spinner" /> Calculando simulación…</div>}{simulation && <><Card title={`Caudal estimado · ciclo ${cycle}`} subtitle={`Comparación con la temperatura de referencia (${fmt(config.reference_temp_c, 0)} °C).`}><div className="chart" role="img" aria-label="Caudal simulado por hora y temperatura"><ResponsiveContainer width="100%" height="100%"><LineChart data={mergeSimulation(simulation.points)} margin={{ top: 10, right: 16, bottom: 5, left: -12 }}><CartesianGrid stroke="#e7ecea" /><XAxis dataKey="tau_h" unit="h" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip formatter={(value: number) => `${fmt(value)} L/s`} /><Legend /><Line dataKey="base" name={`${config.reference_temp_c} °C · referencia`} stroke="#536b85" strokeWidth={2} dot={false} /><Line dataKey="sim" name={`${temperature} °C · simulada`} stroke="#08796c" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div><DataTable rows={simulation.summary} columns={[['Temperatura_C', 'Temperatura (°C)'], ['Qp_inicio_Ls', 'Qp inicial (L/s)'], ['Qp_final_Ls', 'Qp final (L/s)'], ['Qp_promedio_Ls', 'Qp promedio (L/s)'], ['Incremento_Qp_prom_vs_base_pct', 'Cambio promedio (%)']]} /></Card><Notice>La simulación aplica el ajuste térmico del modelo a las mediciones del ciclo. No representa un pronóstico de operación futura.</Notice></>}</>}</div>}

    {tab === 'Cálculo manual' && <div className="section-stack"><div className="section-toolbar"><div><h2>Cálculo de una medición</h2><p>Introduce los valores observados para calcular los indicadores principales.</p></div></div><Card title="Datos de entrada" subtitle="Usa las unidades indicadas para cada variable."><div className="form-grid"><NumberField label="Caudal de permeado Qp (L/s)" value={manual.qp_l_s} min={0.001} onChange={value => setManual({ ...manual, qp_l_s: value })} /><NumberField label="Presión alta (psi)" value={manual.p_high_psi} min={0} onChange={value => setManual({ ...manual, p_high_psi: value })} /><NumberField label="Presión de rechazo (psi)" value={manual.p_reject_psi} min={0} onChange={value => setManual({ ...manual, p_reject_psi: value })} /><NumberField label="TDS de alimentación (mg/L)" value={manual.tds_feed_mg_l} min={0} onChange={value => setManual({ ...manual, tds_feed_mg_l: value })} /><NumberField label="TDS de producto (mg/L)" value={manual.tds_product_mg_l} min={0} onChange={value => setManual({ ...manual, tds_product_mg_l: value })} /></div><div className="form-footer"><button className="button button-primary" onClick={calculate} disabled={manualBusy}>{manualBusy ? 'Calculando…' : 'Calcular indicadores'}</button></div>{manualError && <Notice tone="error">{manualError}</Notice>}</Card>{manualResult && <div className="metric-grid"><Metric label="Flujo Jw" value={fmt(manualResult.Jw, 3)} note="L/m²·h" /><Metric label="Presión osmótica Δπ" value={fmt(manualResult.Delta_pi, 3)} note="psi" /><Metric label="Presión neta NDP" value={fmt(manualResult.NDP, 3)} note="psi" /><Metric label="Permeabilidad Aeff" value={fmt(manualResult.Aeff, 4)} note="L/m²·h·psi" /></div>}<Notice>Si la presión neta no es positiva, la permeabilidad efectiva no se calcula.</Notice></div>}

    {tab === 'Método' && <div className="section-stack"><div className="section-toolbar"><div><h2>Método de análisis</h2><p>Alcance y criterios usados por el modelo.</p></div></div><div className="two-columns"><Card title="Datos requeridos"><p>El libro debe contener la hoja <strong>DATA-OSMOSIS</strong>, con registros desde la fila 8. Se leen fecha (A), hora (D), presiones (L–M), caudales (N–O), TDS y turbidez de alimentación (P–Q), y los indicadores de producto y rechazo (S–V).</p><p>La columna R contiene dureza del producto y no se utiliza en las ecuaciones. Se asumen presiones en psi, caudales en L/s y TDS en mg/L.</p></Card><Card title="Indicadores calculados"><p>El flujo de permeado se obtiene del caudal y el área total de membranas. La presión neta incorpora la diferencia de presión osmótica estimada a partir del TDS. La permeabilidad efectiva es el cociente entre flujo y presión neta positiva.</p><p>Los ciclos se separan por intervalos sin medición mayores al valor configurado. La clasificación compara el inicio y el final de cada ciclo.</p></Card><Card title="Criterio de alerta"><p>Los límites se calculan a partir de las tres primeras mediciones válidas de los ciclos con suficiente información, usando el percentil basal configurado. La evaluación comienza desde la cuarta medición y exige dos candidatos consecutivos.</p><p>Es un indicador exploratorio para revisión técnica. No sustituye la validación de sensores, el criterio de operación de planta ni un diagnóstico de ensuciamiento.</p></Card><Card title="Simulación térmica"><p>El ajuste de temperatura usa el factor de corrección del modelo entregado por la investigación y recalcula la diferencia de presión osmótica. Conserva las demás condiciones observadas del ciclo seleccionado.</p><p>La hoja exportada incluye datos calculados, resúmenes, alertas y la simulación seleccionada.</p></Card></div><div className="method-footnote"><Info size={17} /><span>Modelo basado en el trabajo entregado por la Universidad Técnica de Manabí para Aquaher. La implementación corrige la asignación de columnas del archivo operativo verificado.</span></div></div>}
  </main><footer className="site-footer"><div>Aquaher · Análisis operativo</div><div>Modelo fenomenológico de ósmosis inversa</div></footer></>
}

function CycleSelect({ cycles, value, onChange }: { cycles: RecordRow[]; value: number; onChange: (value: number) => void }) {
  return <label className="field select-field"><span>Ciclo</span><select value={value} onChange={event => onChange(Number(event.target.value))}>{cycles.map(row => <option key={String(row.Ciclo)} value={Number(row.Ciclo)}>Ciclo {row.Ciclo}</option>)}</select></label>
}

type TableColumn = [string, string, ((value: unknown) => string)?]
function DataTable({ rows, columns, onRowClick }: { rows: RecordRow[]; columns: TableColumn[]; onRowClick?: (row: RecordRow) => void }) {
  return <div className="table-scroll"><table><thead><tr>{columns.map(([, label]) => <th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index} onClick={onRowClick ? () => onRowClick(row) : undefined} className={onRowClick ? 'clickable-row' : ''}>{columns.map(([key, , formatter]) => <td key={key}>{formatter ? formatter(row[key]) : typeof row[key] === 'number' ? fmt(row[key], key === 'Ciclo' || key === 'n' ? 0 : 2) : String(row[key] ?? '—')}</td>)}</tr>)}</tbody></table></div>
}

function mergeSimulation(points: RecordRow[]) {
  const temperatures = [...new Set(points.map(row => n(row, 'Temperatura_C')))]
  const base = temperatures[0]
  const target = temperatures[temperatures.length - 1]
  const merged = new Map<number, { tau_h: number; base?: number; sim?: number }>()
  for (const point of points) {
    const time = n(point, 'tau_h')
    const item = merged.get(time) ?? { tau_h: time }
    if (n(point, 'Temperatura_C') === base) item.base = n(point, 'Qp_sim_Ls')
    if (n(point, 'Temperatura_C') === target) item.sim = n(point, 'Qp_sim_Ls')
    merged.set(time, item)
  }
  return [...merged.values()].sort((a, b) => a.tau_h - b.tau_h)
}

function normalizedCycle(rows: RecordRow[]) {
  const first = rows[0]
  if (!first) return []
  return rows.map(row => ({
    tau_h: n(row, 'tau_h'),
    Qp: n(first, 'Qp') > 0 ? 100 * n(row, 'Qp') / n(first, 'Qp') : null,
    NDP: n(first, 'NDP') > 0 ? 100 * n(row, 'NDP') / n(first, 'NDP') : null,
    Aeff: n(first, 'Aeff') > 0 && row.Aeff !== null ? 100 * n(row, 'Aeff') / n(first, 'Aeff') : null,
  }))
}

export default App

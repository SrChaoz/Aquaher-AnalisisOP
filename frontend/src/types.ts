export type Config = {
  membranes: number
  element_area_m2: number
  reference_temp_c: number
  permeate_pressure_psi: number
  max_gap_h: number
  basal_quantile: number
  diagnostic_band_pct: number
}

export type RecordRow = Record<string, number | string | boolean | null>
export type Analysis = {
  summary: {
    read_rows: number
    operational_rows: number
    cycles: number
    alert_cycles: number
    invalid_ndp: number
    limit_a: number | null
    limit_ndp: number | null
    first_date: string
    last_date: string
  }
  cycles: RecordRow[]
  operational: RecordRow[]
  monitoring: RecordRow[]
  first_alerts: RecordRow[]
}
export type Simulation = { points: RecordRow[]; summary: RecordRow[] }

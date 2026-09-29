import type { Config, Analysis, Simulation } from './types'

export async function apiJson<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`/api/${path}`, init)
  if (!response.ok) {
    let message = `Error del servidor (${response.status}).`
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (response.status === 422) message = 'Revisa los valores ingresados.'
    } catch { /* Keep the status message. */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

function uploadBody(file: File, config: Config): FormData {
  const body = new FormData()
  body.append('file', file)
  body.append('config', JSON.stringify(config))
  return body
}

export function analyzeFile(file: File, config: Config): Promise<Analysis> {
  return apiJson('analyze', { method: 'POST', body: uploadBody(file, config) })
}

export function simulate(operational: Analysis['operational'], cycle: number, temperature_c: number, config: Config): Promise<Simulation> {
  return apiJson('simulate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ operational, cycle, temperature_c, config }) })
}

export async function exportFile(file: File, config: Config, cycle: number, temperature: number): Promise<void> {
  const body = uploadBody(file, config)
  body.append('cycle', String(cycle))
  body.append('temperature', String(temperature))
  const response = await fetch('/api/export', { method: 'POST', body })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : 'No se pudo generar el archivo.')
  }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'Resultados_Aquaher_RO.xlsx'
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

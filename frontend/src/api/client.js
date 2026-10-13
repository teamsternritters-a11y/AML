const BASE = '/api'

async function request(method, path, data, params) {
  let url = BASE + path
  if (params && Object.keys(params).length > 0) {
    const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([,v]) => v != null && v !== '')))
    url += '?' + q.toString()
  }
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } }
    if (data != null) opts.body = JSON.stringify(data)
    const res = await fetch(url, opts)
    if (!res.ok) {
      let detail = res.statusText
      try { const j = await res.json(); detail = j.detail || JSON.stringify(j) } catch {}
      throw new Error(`HTTP ${res.status}: ${detail}`)
    }
    return res.json()
  } catch (err) {
    if (err.name === 'TypeError') throw new Error('Backend unreachable — is the API server running?')
    throw err
  }
}

export const get  = (path, params) => request('GET',  path, null, params)
export const post = (path, body)   => request('POST', path, body, null)
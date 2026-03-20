import React, { useState, useEffect, useCallback } from 'react'
import {
  Calendar, Mail, Settings, Activity, RefreshCw,
  CheckCircle, XCircle, Clock, AlertTriangle, Send, ChevronDown, ChevronUp
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL ?? ''

const s = {
  app: { minHeight: '100vh', background: '#0f172a', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif' },
  header: { background: '#1e293b', borderBottom: '1px solid #334155', padding: '0 2rem', display: 'flex', alignItems: 'center', gap: '1rem', height: 64 },
  logo: { fontSize: 22, fontWeight: 700, color: '#818cf8', letterSpacing: '-0.5px' },
  badge: { background: '#312e81', color: '#a5b4fc', fontSize: 11, padding: '2px 8px', borderRadius: 99, fontWeight: 600 },
  nav: { display: 'flex', gap: '0.25rem', marginLeft: 'auto' },
  navBtn: (active) => ({ background: active ? '#334155' : 'transparent', color: active ? '#e2e8f0' : '#94a3b8', border: 'none', borderRadius: 8, padding: '6px 14px', cursor: 'pointer', fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }),
  main: { maxWidth: 1100, margin: '0 auto', padding: '2rem 1.5rem' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '2rem' },
  card: { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: '1.25rem' },
  cardTitle: { fontSize: 13, color: '#94a3b8', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 },
  cardValue: { fontSize: 28, fontWeight: 700, color: '#e2e8f0' },
  cardSub: { fontSize: 12, color: '#64748b', marginTop: 4 },
  section: { background: '#1e293b', border: '1px solid #334155', borderRadius: 12, marginBottom: '1.5rem', overflow: 'hidden' },
  sectionHeader: { padding: '1rem 1.25rem', borderBottom: '1px solid #334155', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle: { fontWeight: 600, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { padding: '10px 16px', textAlign: 'left', fontSize: 12, color: '#64748b', fontWeight: 600, borderBottom: '1px solid #334155', textTransform: 'uppercase', letterSpacing: '0.05em' },
  td: { padding: '12px 16px', fontSize: 13, borderBottom: '1px solid #1e293b', verticalAlign: 'top' },
  pill: (color) => ({ display: 'inline-block', padding: '2px 10px', borderRadius: 99, fontSize: 11, fontWeight: 600, background: color + '22', color }),
  btn: (variant = 'primary') => ({
    background: variant === 'primary' ? '#4f46e5' : variant === 'danger' ? '#dc2626' : '#334155',
    color: '#fff', border: 'none', borderRadius: 8, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6
  }),
  input: { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e2e8f0', padding: '8px 12px', fontSize: 13, width: '100%', outline: 'none' },
  label: { fontSize: 12, color: '#94a3b8', marginBottom: 4, display: 'block' },
  row: { display: 'flex', gap: '1rem', alignItems: 'flex-start' },
  col: { flex: 1 },
  toast: (type) => ({
    position: 'fixed', bottom: 24, right: 24, background: type === 'error' ? '#7f1d1d' : '#14532d',
    border: `1px solid ${type === 'error' ? '#dc2626' : '#16a34a'}`, color: '#fff',
    padding: '12px 20px', borderRadius: 10, fontSize: 13, zIndex: 9999, maxWidth: 360
  }),
  empty: { padding: '2rem', textAlign: 'center', color: '#475569', fontSize: 13 },
  spinner: { display: 'inline-block', width: 16, height: 16, border: '2px solid #334155', borderTopColor: '#818cf8', borderRadius: '50%', animation: 'spin 0.7s linear infinite' },
}

function useApi(path, deps = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const refetch = useCallback(() => {
    setLoading(true)
    fetch(`${API}${path}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(d => { setData(d); setError(null) })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [path])
  useEffect(() => { refetch() }, [refetch, ...deps])
  return { data, loading, error, refetch }
}

function StatusDot({ ok }) {
  return <span style={{ width: 8, height: 8, borderRadius: '50%', background: ok ? '#22c55e' : '#ef4444', display: 'inline-block', marginRight: 6 }} />
}

function Toast({ msg, type, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 4000); return () => clearTimeout(t) }, [])
  return <div style={s.toast(type)}>{msg}</div>
}

function Spinner() {
  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      <span style={s.spinner} />
    </>
  )
}

// ── Dashboard tab ──────────────────────────────────────────────────────────
function Dashboard({ health, bookings, prefs }) {
  const totalBookings = bookings?.length ?? 0
  const todayBookings = bookings?.filter(b => b.slot_start?.startsWith(new Date().toISOString().slice(0, 10))).length ?? 0
  const maxHours = prefs?.max_daily_hours ?? 4

  return (
    <>
      <div style={s.grid}>
        <div style={s.card}>
          <div style={s.cardTitle}><Activity size={14} /> API Status</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
            <StatusDot ok={health?.status === 'ok'} />
            <span style={{ fontSize: 16, fontWeight: 600 }}>{health?.status === 'ok' ? 'Online' : 'Offline'}</span>
          </div>
          <div style={s.cardSub}>FastAPI backend</div>
        </div>
        <div style={s.card}>
          <div style={s.cardTitle}><Calendar size={14} /> Total Bookings</div>
          <div style={s.cardValue}>{totalBookings}</div>
          <div style={s.cardSub}>{todayBookings} today</div>
        </div>
        <div style={s.card}>
          <div style={s.cardTitle}><Clock size={14} /> Daily Limit</div>
          <div style={s.cardValue}>{maxHours}h</div>
          <div style={s.cardSub}>max meetings per day</div>
        </div>
        <div style={s.card}>
          <div style={s.cardTitle}><Mail size={14} /> VIP Contacts</div>
          <div style={s.cardValue}>{prefs?.vip_emails?.length ?? 0}</div>
          <div style={s.cardSub}>priority scheduling</div>
        </div>
      </div>

      <div style={s.section}>
        <div style={s.sectionHeader}>
          <span style={s.sectionTitle}><Calendar size={15} /> Recent Bookings</span>
        </div>
        {!bookings || bookings.length === 0
          ? <div style={s.empty}>No bookings yet. Send a scheduling email to get started.</div>
          : (
            <table style={s.table}>
              <thead>
                <tr>
                  {['Event ID', 'Participants', 'Start', 'End'].map(h => <th key={h} style={s.th}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {bookings.slice(0, 10).map(b => (
                  <tr key={b.id}>
                    <td style={s.td}><code style={{ fontSize: 11, color: '#818cf8' }}>{b.event_id?.slice(0, 16)}…</code></td>
                    <td style={s.td}>{(b.participants || []).join(', ')}</td>
                    <td style={s.td}>{b.slot_start ? new Date(b.slot_start).toLocaleString() : '—'}</td>
                    <td style={s.td}>{b.slot_end ? new Date(b.slot_end).toLocaleString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </div>
    </>
  )
}

// ── Trigger tab ────────────────────────────────────────────────────────────
function TriggerEmail({ onToast }) {
  const [form, setForm] = useState({
    sender: 'test@example.com',
    recipients: '',
    subject: 'Can we schedule a meeting?',
    body: 'Hi, I would like to schedule a 1-hour meeting next Tuesday at 10am or 2pm. Let me know what works.',
  })
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    setLoading(true)
    try {
      const payload = {
        message_id: `test-${Date.now()}@patrai`,
        thread_id: `thread-${Date.now()}`,
        sender: form.sender,
        recipients: form.recipients.split(',').map(s => s.trim()).filter(Boolean),
        subject: form.subject,
        body: form.body,
        timestamp: new Date().toISOString(),
      }
      const r = await fetch(`${API}/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const d = await r.json()
      if (r.ok) onToast(`Task queued: ${d.task_id}`, 'success')
      else onToast(`Error: ${JSON.stringify(d)}`, 'error')
    } catch (e) {
      onToast(`Network error: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.section}>
      <div style={s.sectionHeader}>
        <span style={s.sectionTitle}><Send size={15} /> Trigger Email Processing</span>
      </div>
      <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={s.row}>
          <div style={s.col}>
            <label style={s.label}>Sender</label>
            <input style={s.input} value={form.sender} onChange={e => setForm(f => ({ ...f, sender: e.target.value }))} />
          </div>
          <div style={s.col}>
            <label style={s.label}>Recipients (comma-separated)</label>
            <input style={s.input} value={form.recipients} onChange={e => setForm(f => ({ ...f, recipients: e.target.value }))} placeholder="alice@example.com, bob@example.com" />
          </div>
        </div>
        <div>
          <label style={s.label}>Subject</label>
          <input style={s.input} value={form.subject} onChange={e => setForm(f => ({ ...f, subject: e.target.value }))} />
        </div>
        <div>
          <label style={s.label}>Body</label>
          <textarea style={{ ...s.input, minHeight: 120, resize: 'vertical' }} value={form.body} onChange={e => setForm(f => ({ ...f, body: e.target.value }))} />
        </div>
        <div>
          <button style={s.btn()} onClick={submit} disabled={loading}>
            {loading ? <Spinner /> : <Send size={14} />} Process Email
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Preferences tab ────────────────────────────────────────────────────────
function Preferences({ onToast }) {
  const { data, loading, refetch } = useApi('/preferences')
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [vipInput, setVipInput] = useState('')

  useEffect(() => { if (data) setForm({ ...data, vip_emails: data.vip_emails || [] }) }, [data])

  const save = async () => {
    setSaving(true)
    try {
      const r = await fetch(`${API}/preferences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, focus_blocks: [] }),
      })
      if (r.ok) { onToast('Preferences saved', 'success'); refetch() }
      else onToast('Save failed', 'error')
    } catch (e) { onToast(`Error: ${e}`, 'error') }
    finally { setSaving(false) }
  }

  const addVip = () => {
    if (vipInput.trim()) {
      setForm(f => ({ ...f, vip_emails: [...(f.vip_emails || []), vipInput.trim()] }))
      setVipInput('')
    }
  }

  if (loading || !form) return <div style={s.empty}><Spinner /></div>

  return (
    <div style={s.section}>
      <div style={s.sectionHeader}>
        <span style={s.sectionTitle}><Settings size={15} /> Scheduling Preferences</span>
        <button style={s.btn()} onClick={save} disabled={saving}>
          {saving ? <Spinner /> : <CheckCircle size={14} />} Save
        </button>
      </div>
      <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div style={{ maxWidth: 280 }}>
          <label style={s.label}>Max Daily Meeting Hours</label>
          <input style={s.input} type="number" min={0.5} max={12} step={0.5}
            value={form.max_daily_hours}
            onChange={e => setForm(f => ({ ...f, max_daily_hours: parseFloat(e.target.value) }))} />
        </div>
        <div>
          <label style={s.label}>VIP Emails (get first pick of slots)</label>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            <input style={{ ...s.input, flex: 1 }} value={vipInput} onChange={e => setVipInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && addVip()} placeholder="vip@example.com" />
            <button style={s.btn('secondary')} onClick={addVip}>Add</button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(form.vip_emails || []).map(email => (
              <span key={email} style={{ ...s.pill('#818cf8'), cursor: 'pointer', userSelect: 'none' }}
                onClick={() => setForm(f => ({ ...f, vip_emails: f.vip_emails.filter(e => e !== email) }))}>
                {email} ×
              </span>
            ))}
            {form.vip_emails?.length === 0 && <span style={{ color: '#475569', fontSize: 12 }}>No VIP emails. Click × to remove.</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Negotiation tab ────────────────────────────────────────────────────────
function Negotiations() {
  const [threadId, setThreadId] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const lookup = async () => {
    if (!threadId.trim()) return
    setLoading(true); setError(null)
    try {
      const r = await fetch(`${API}/negotiation/${encodeURIComponent(threadId.trim())}`)
      if (r.ok) setResult(await r.json())
      else { setResult(null); setError('Not found') }
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  const stateColor = { proposed: '#f59e0b', counter_proposed: '#f97316', escalated: '#ef4444', resolved: '#22c55e' }

  return (
    <div style={s.section}>
      <div style={s.sectionHeader}>
        <span style={s.sectionTitle}><AlertTriangle size={15} /> Negotiation State Lookup</span>
      </div>
      <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input style={{ ...s.input, flex: 1 }} value={threadId} onChange={e => setThreadId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && lookup()} placeholder="Enter thread_id…" />
          <button style={s.btn()} onClick={lookup} disabled={loading}>
            {loading ? <Spinner /> : 'Lookup'}
          </button>
        </div>
        {error && <div style={{ color: '#f87171', fontSize: 13 }}>{error}</div>}
        {result && (
          <div style={{ background: '#0f172a', borderRadius: 10, padding: '1rem', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span style={s.pill(stateColor[result.state] || '#94a3b8')}>{result.state}</span>
              <span style={{ fontSize: 13, color: '#94a3b8' }}>Round {result.round_count}</span>
            </div>
            <div style={{ fontSize: 12, color: '#64748b' }}>Thread: <code style={{ color: '#818cf8' }}>{result.thread_id}</code></div>
            {result.history?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>History</div>
                {result.history.map((h, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#cbd5e1', padding: '4px 0', borderTop: '1px solid #1e293b' }}>{h}</div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Root App ───────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('dashboard')
  const [toast, setToast] = useState(null)

  const { data: health, refetch: refetchHealth } = useApi('/health')
  const { data: bookings, refetch: refetchBookings } = useApi('/bookings')
  const { data: prefs } = useApi('/preferences')

  const onToast = (msg, type = 'success') => setToast({ msg, type })

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: <Activity size={14} /> },
    { id: 'trigger', label: 'Trigger', icon: <Send size={14} /> },
    { id: 'preferences', label: 'Preferences', icon: <Settings size={14} /> },
    { id: 'negotiation', label: 'Negotiation', icon: <AlertTriangle size={14} /> },
  ]

  return (
    <div style={s.app}>
      <header style={s.header}>
        <span style={s.logo}>PatrAI</span>
        <span style={s.badge}>AI Email Agent</span>
        <nav style={s.nav}>
          {tabs.map(t => (
            <button key={t.id} style={s.navBtn(tab === t.id)} onClick={() => setTab(t.id)}>
              {t.icon}{t.label}
            </button>
          ))}
          <button style={s.navBtn(false)} onClick={() => { refetchHealth(); refetchBookings() }} title="Refresh">
            <RefreshCw size={14} />
          </button>
        </nav>
      </header>

      <main style={s.main}>
        {tab === 'dashboard' && <Dashboard health={health} bookings={bookings} prefs={prefs} />}
        {tab === 'trigger' && <TriggerEmail onToast={onToast} />}
        {tab === 'preferences' && <Preferences onToast={onToast} />}
        {tab === 'negotiation' && <Negotiations />}
      </main>

      {toast && <Toast msg={toast.msg} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

// ── Helpers ────────────────────────────────────────────────

const priorityBadge = (p) => ({
  High:   'bg-red-100 text-red-700 border border-red-200',
  Medium: 'bg-yellow-100 text-yellow-700 border border-yellow-200',
  Low:    'bg-green-100 text-green-700 border border-green-200',
}[p] ?? 'bg-gray-100 text-gray-600')

const statusBadge = (s) => ({
  Pending:      'bg-blue-50 text-blue-700',
  'In Progress':'bg-purple-50 text-purple-700',
  Done:         'bg-green-50 text-green-700',
  Cancelled:    'bg-gray-50 text-gray-400',
}[s] ?? 'bg-gray-50 text-gray-600')

const fmt = (iso) => iso
  ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  : '—'

// ── Chat Panel ─────────────────────────────────────────────

function ChatPanel({ onTranscriptProcessed }) {
  const WELCOME = '👋 **Welcome to MeetingMind!**\n\nI\'m powered by **7 specialized agents** working together to process your meetings.\n\n**Try:**\n- Paste any meeting transcript (500+ chars)\n- "What tasks are pending?"\n- "Who has the most tasks?"\n- "What\'s overdue?"'

  const [messages, setMessages] = useState([{ role: 'assistant', text: WELCOME }])
  const [input, setInput]       = useState('')
  const [loading, setLoading]   = useState(false)
  const [sessionId]             = useState(() => {
    const k = 'mm_sid'
    return localStorage.getItem(k) || (() => {
      const id = crypto.randomUUID()
      localStorage.setItem(k, id)
      return id
    })()
  })
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(m => [...m, { role: 'user', text: msg }])
    setLoading(true)

    try {
      const res  = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, session_id: sessionId }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Server error')
      const reply = data.response || '⚠️ Empty response from agent.'
      setMessages(m => [...m, { role: 'assistant', text: reply }])
      if (reply.includes('Meeting Processed Successfully')) {
        onTranscriptProcessed?.()
      }
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', text: `⚠️ ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const STAGES = ['Summary', 'Save', 'Analyse ×3', 'Tasks+Cal', 'Brief']

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-4 py-3 bg-indigo-600 text-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold tracking-tight">🧠 MeetingMind</span>
          <span className="text-xs bg-indigo-500 px-2 py-0.5 rounded-full">7 Agents</span>
        </div>
        <span className="text-xs text-indigo-200">AI Meeting Intelligence</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === 'user'
                ? 'bg-indigo-600 text-white rounded-br-sm'
                : 'bg-gray-100 text-gray-800 rounded-bl-sm'
            }`}>
              {m.role === 'assistant' ? (
                <div
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: marked.parse(m.text) }}
                />
              ) : (
                <span className="whitespace-pre-wrap">{m.text}</span>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3 max-w-[88%]">
              <p className="text-xs text-gray-500 mb-2 flex items-center gap-1">
                <span className="animate-spin inline-block">⚙️</span>
                Processing through 7 agents…
              </p>
              <div className="flex flex-wrap gap-1">
                {STAGES.map((s, i) => (
                  <span
                    key={s}
                    className="text-xs bg-indigo-100 text-indigo-600 px-2 py-0.5 rounded-full animate-pulse"
                    style={{ animationDelay: `${i * 0.4}s` }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-200 shrink-0">
        <div className="flex gap-2">
          <textarea
            className="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-indigo-400 transition-colors"
            rows={3}
            placeholder="Paste a meeting transcript or ask a question…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={loading}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-4 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1">Enter to send · Shift+Enter for newline</p>
      </div>
    </div>
  )
}

// ── Task Board ─────────────────────────────────────────────

function TaskBoard({ refreshTrigger }) {
  const [tasks,   setTasks]   = useState([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const qs  = filter !== 'all' ? `?status=${encodeURIComponent(filter)}` : ''
      const res = await fetch(`/api/tasks${qs}`)
      const d   = await res.json()
      setTasks(d.tasks || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load, refreshTrigger])

  const filters = ['all', 'Pending', 'In Progress', 'Done']

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between shrink-0">
        <span className="text-sm font-semibold text-gray-700">
          {tasks.length} task{tasks.length !== 1 ? 's' : ''}
        </span>
        <div className="flex gap-1 items-center">
          {filters.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === f ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {f === 'all' ? 'All' : f}
            </button>
          ))}
          <button
            onClick={load}
            className="ml-1 px-3 py-1 rounded-full text-xs bg-gray-100 text-gray-600 hover:bg-gray-200"
          >
            ↻
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-2">
        {loading ? (
          <div className="text-center py-12 text-gray-400 text-sm">Loading tasks…</div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No tasks found.<br/>
            <span className="text-xs">Process a transcript in the chat to extract tasks.</span>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400 border-b border-gray-100">
                <th className="text-left py-2 pr-3 font-medium">Task</th>
                <th className="text-left py-2 pr-3 font-medium">Owner</th>
                <th className="text-left py-2 pr-3 font-medium">Priority</th>
                <th className="text-left py-2 pr-3 font-medium">Deadline</th>
                <th className="text-left py-2 pr-3 font-medium">Status</th>
                <th className="text-left py-2 font-medium">Meeting</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {tasks.map(t => (
                <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                  <td className="py-2 pr-3 text-gray-800 max-w-[180px]">
                    <span className="truncate block" title={t.task_name}>{t.task_name}</span>
                  </td>
                  <td className="py-2 pr-3 text-gray-500 text-xs whitespace-nowrap">{t.owner || '—'}</td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${priorityBadge(t.priority)}`}>
                      {t.priority}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-gray-500 text-xs whitespace-nowrap">
                    {t.deadline ? t.deadline.split('T')[0] : '—'}
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${statusBadge(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400 text-xs max-w-[140px]">
                    <span className="truncate block" title={t.meeting_summary || ''}>
                      {t.meeting_summary ? t.meeting_summary.split('.')[0].slice(0, 40) + (t.meeting_summary.length > 40 ? '…' : '') : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── Meetings Panel ─────────────────────────────────────────

function MeetingsPanel() {
  const [meetings, setMeetings] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    fetch('/api/meetings')
      .then(r => r.json())
      .then(d => setMeetings(d.meetings || []))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-100 shrink-0">
        <span className="text-sm font-semibold text-gray-700">{meetings.length} meeting{meetings.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading ? (
          <div className="text-center py-12 text-gray-400 text-sm">Loading meetings…</div>
        ) : meetings.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No meetings yet.<br/>
            <span className="text-xs">Process a transcript to save a meeting.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {meetings.map(m => (
              <div key={m.meeting_id} className="border border-gray-200 rounded-xl overflow-hidden">
                <button
                  onClick={() => setExpanded(expanded === m.meeting_id ? null : m.meeting_id)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-800 leading-tight">{m.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{fmt(m.created_at)}</p>
                  </div>
                  <span className="text-gray-300 text-xs ml-2">{expanded === m.meeting_id ? '▲' : '▼'}</span>
                </button>
                {expanded === m.meeting_id && (
                  <div className="px-4 pb-3 pt-2 text-sm text-gray-600 border-t border-gray-100 leading-relaxed">
                    {m.summary_preview || 'No summary available.'}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Analytics Panel ────────────────────────────────────────

function StatCard({ label, value, color }) {
  return (
    <div className={`rounded-xl p-3 ${color}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs mt-0.5 opacity-80">{label}</p>
    </div>
  )
}

function QualityWidget() {
  const [scores, setScores] = useState([])

  useEffect(() => {
    fetch('/api/quality')
      .then(r => r.json())
      .then(d => setScores(d.scores || []))
      .catch(console.error)
  }, [])

  if (!scores.length) return null
  const q = scores[0]

  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Latest Quality Score</h3>
      <div className="bg-indigo-50 rounded-xl p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-semibold text-indigo-800">Overall</span>
          <span className="text-xl font-bold text-indigo-700">{q.overall_score?.toFixed(1) ?? '—'}/5.0</span>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-indigo-700">
          {[['Summary', q.summary_quality], ['Tasks', q.task_extraction_completeness],
            ['Priority', q.priority_accuracy], ['Owners', q.owner_attribution]].map(([k, v]) => (
            <span key={k} className="flex justify-between">
              <span>{k}</span>
              <span className="font-semibold">{v ?? '—'}/5</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

function AnalyticsPanel() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/analytics')
      .then(r => r.json())
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="p-4 text-center py-12 text-gray-400 text-sm">Loading analytics…</div>
  if (!data)   return null

  const velocity  = data.velocity?.velocity  ?? data.velocity  ?? {}
  const owners    = data.ownership?.owners   ?? []
  const overdueList = data.overdue?.tasks    ?? []
  const topics    = (data.topics?.topics     ?? []).slice(0, 14)

  const openTasks = (velocity.total_tasks ?? 0) - (velocity.completed_tasks ?? 0)

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-4 space-y-5">
      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Meetings"  value={velocity.total_meetings ?? 0} color="bg-indigo-50 text-indigo-700" />
        <StatCard label="Open Tasks" value={openTasks > 0 ? openTasks : 0} color="bg-amber-50 text-amber-700" />
        <StatCard label="Overdue"   value={overdueList.length}            color="bg-red-50 text-red-700" />
      </div>

      {/* Ownership */}
      {owners.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Task Ownership</h3>
          <div className="space-y-2">
            {owners.slice(0, 6).map((o, i) => {
              const maxTasks = owners[0]?.total_tasks || 1
              const pct = Math.round((o.total_tasks / maxTasks) * 100)
              return (
                <div key={o.owner}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="font-medium text-gray-700">{o.owner}</span>
                    <span className="text-gray-400">{o.total_tasks} tasks · {o.completion_pct ?? 0}% done</span>
                  </div>
                  <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${pct}%`,
                        backgroundColor: ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6'][i % 6],
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Overdue */}
      {overdueList.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">⚠️ Overdue Tasks</h3>
          <div className="space-y-1.5">
            {overdueList.slice(0, 5).map(t => (
              <div key={t.id} className="flex justify-between items-center bg-red-50 rounded-lg px-3 py-2 text-xs">
                <span className="text-gray-700 truncate max-w-[58%]" title={t.task_name}>{t.task_name}</span>
                <span className="text-red-600 font-medium ml-2 whitespace-nowrap">
                  {t.owner || '?'} · {t.days_overdue}d late
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recurring topics */}
      {topics.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Recurring Topics</h3>
          <div className="flex flex-wrap gap-1.5">
            {topics.map(t => (
              <span key={t.word} className="px-2.5 py-1 bg-gray-100 text-gray-700 rounded-full text-xs">
                {t.word}
                <span className="text-gray-400 ml-1">×{t.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <QualityWidget />
    </div>
  )
}

// ── Root App ───────────────────────────────────────────────

const TABS = [
  { id: 'tasks',    label: '✅ Tasks' },
  { id: 'meetings', label: '📋 Meetings' },
  { id: 'analytics',label: '📊 Analytics' },
]

export default function App() {
  const [tab,            setTab]            = useState('tasks')
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  return (
    <div className="h-screen flex overflow-hidden bg-gray-50 font-sans antialiased">
      {/* Left — Chat (40%) */}
      <div className="w-2/5 min-w-72 max-w-lg border-r border-gray-200 flex flex-col overflow-hidden shadow-sm">
        <ChatPanel onTranscriptProcessed={() => setRefreshTrigger(n => n + 1)} />
      </div>

      {/* Right — Dashboard (60%) */}
      <div className="flex-1 flex flex-col overflow-hidden bg-white">
        {/* Tab bar */}
        <div className="flex border-b border-gray-200 px-4 shrink-0 bg-white">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-400 hover:text-gray-600'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-hidden">
          {tab === 'tasks'     && <TaskBoard     refreshTrigger={refreshTrigger} />}
          {tab === 'meetings'  && <MeetingsPanel />}
          {tab === 'analytics' && <AnalyticsPanel />}
        </div>
      </div>
    </div>
  )
}

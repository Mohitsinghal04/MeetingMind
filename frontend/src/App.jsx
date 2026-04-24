import { useState, useEffect, useRef, useCallback } from 'react'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

// ── Helpers ────────────────────────────────────────────────

const priorityBadge = (p) => ({
  High:   'bg-red-100 text-red-700 border border-red-200',
  Medium: 'bg-amber-100 text-amber-700 border border-amber-200',
  Low:    'bg-emerald-100 text-emerald-700 border border-emerald-200',
}[p] ?? 'bg-gray-100 text-gray-500')

const statusBadge = (s) => ({
  Pending:      'bg-sky-50 text-sky-700 border border-sky-200',
  'In Progress':'bg-violet-50 text-violet-700 border border-violet-200',
  Done:         'bg-emerald-50 text-emerald-700 border border-emerald-200',
  Cancelled:    'bg-gray-50 text-gray-400 border border-gray-200',
}[s] ?? 'bg-gray-50 text-gray-500')

const fmtDate = (val) => {
  if (!val) return '—'
  const s = String(val)
  // Handle "By July 24, 2026", "Week of July 13, 2026", ISO dates
  if (s.includes('-')) {
    const d = new Date(s)
    return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  // Shorten natural language dates
  return s.replace(/^(By|Before|Week of|Before )\s*/i, '').slice(0, 18)
}

const meetingTitle = (summary) => {
  if (!summary) return '—'
  return summary.split('.')[0].replace(/^The /i, '').slice(0, 35)
}

// Detect if a message is a task-update command
const isTaskUpdate = (msg) =>
  /\b(mark|done|complete|in progress|update|finish|finished|status)\b/i.test(msg)

// Detect if agent response confirms a task was updated
const isTaskUpdateConfirm = (reply) =>
  /marked as|updated to|status.*changed|task.*done|task.*progress|task.*complete/i.test(reply)

// ── Chat Panel ─────────────────────────────────────────────

const WELCOME = '👋 **Welcome to MeetingMind!**\n\nI\'m powered by **8 specialized agents** working together to process your meetings.\n\n**Try:**\n- Paste any meeting transcript (500+ chars)\n- "What tasks are pending?"\n- "Who has the most tasks?"\n- "What\'s overdue?"'

function ChatPanel({ onTranscriptProcessed, onTaskUpdated }) {
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
    const wasTaskCommand = isTaskUpdate(msg)

    try {
      const res = await fetch('/api/chat', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ message: msg, session_id: sessionId }),
      })
      if (!res.ok) {
        let detail = `Server error (${res.status})`
        try { const d = await res.json(); detail = d.detail || detail } catch {}
        throw new Error(detail)
      }

      // Read SSE stream — heartbeat lines keep connection alive, data line is the response
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let reply  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep incomplete last line
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'error') throw new Error(evt.detail || 'Agent error')
            if (evt.type === 'response') reply = evt.response || '⚠️ No response.'
          } catch (parseErr) {
            if (parseErr.message !== 'Agent error' && !parseErr.message.startsWith('Agent')) continue
            throw parseErr
          }
        }
      }

      if (!reply) reply = '⚠️ No response received from agents.'
      setMessages(m => [...m, { role: 'assistant', text: reply }])

      if (reply.includes('Meeting Processed Successfully') || reply.includes('meeting processed')) {
        onTranscriptProcessed?.()
      } else if (wasTaskCommand && isTaskUpdateConfirm(reply)) {
        onTaskUpdated?.()
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

  const STAGES = ['Analyse', 'Save', 'Schedule', 'Brief']

  return (
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-indigo-600 to-indigo-500 text-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight">🧠 MeetingMind</span>
          <span className="text-xs bg-white/20 backdrop-blur px-2.5 py-0.5 rounded-full font-medium">8 Agents</span>
        </div>
        <span className="text-xs text-indigo-200 font-medium">AI Meeting Intelligence</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4 bg-gray-50">
        {messages.map((m, i) => (
          <div key={i} className={`flex min-w-0 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {m.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm mr-2 mt-0.5 shrink-0">🧠</div>
            )}
            <div className={`max-w-[85%] min-w-0 rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              m.role === 'user'
                ? 'bg-indigo-600 text-white rounded-br-none'
                : 'bg-white text-gray-800 rounded-bl-none border border-gray-100'
            }`} style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
              {m.role === 'assistant' ? (
                <div
                  className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-pre:overflow-x-auto prose-pre:whitespace-pre-wrap"
                  style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
                  dangerouslySetInnerHTML={{ __html: (() => { try { return marked.parse(m.text) } catch { return m.text } })() }}
                />
              ) : (
                <span style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{m.text}</span>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start items-start gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm shrink-0">🧠</div>
            <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
              <p className="text-xs text-gray-500 mb-2.5 flex items-center gap-1.5 font-medium">
                <span className="animate-spin inline-block">⚙️</span>
                Agents working…
              </p>
              <div className="flex gap-1.5">
                {STAGES.map((s, i) => (
                  <span
                    key={s}
                    className="text-xs bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-full animate-pulse font-medium"
                    style={{ animationDelay: `${i * 0.3}s` }}
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
      <div className="px-4 py-3 border-t border-gray-200 bg-white shrink-0">
        <div className="flex gap-2 items-end">
          <textarea
            className="flex-1 resize-none border border-gray-200 rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-50 transition-all bg-gray-50 placeholder-gray-400"
            rows={2}
            placeholder="Paste a transcript or ask a question…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={loading}
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
          >
            Send
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-1.5 pl-1">Enter to send · Shift+Enter for newline</p>
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

  const filters = [
    { id: 'all',         label: 'All' },
    { id: 'Pending',     label: 'Pending' },
    { id: 'In Progress', label: 'In Progress' },
    { id: 'Done',        label: 'Done' },
  ]

  const counts = {
    all:          tasks.length,
    Pending:      tasks.filter(t => t.status === 'Pending').length,
    'In Progress':tasks.filter(t => t.status === 'In Progress').length,
    Done:         tasks.filter(t => t.status === 'Done').length,
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white">
        <div className="flex items-center gap-1.5">
          {filters.map(f => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filter === f.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {f.label}
              <span className={`ml-1.5 text-xs ${filter === f.id ? 'opacity-80' : 'text-gray-400'}`}>
                {filter === f.id
                  ? tasks.length
                  : f.id === 'all'
                    ? counts.all
                    : counts[f.id] ?? 0}
              </span>
            </button>
          ))}
        </div>
        <button
          onClick={load}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          title="Refresh"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center h-40 text-gray-400 text-sm gap-2">
            <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
            </svg>
            Loading tasks…
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-center gap-2">
            <span className="text-4xl">📋</span>
            <p className="text-gray-500 font-medium text-sm">No tasks found</p>
            <p className="text-gray-400 text-xs">Process a transcript in the chat to extract tasks</p>
          </div>
        ) : (
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-gray-50 z-10">
              <tr className="text-xs uppercase text-gray-400 border-b border-gray-200">
                <th className="text-left py-2.5 px-5 font-semibold">Task</th>
                <th className="text-left py-2.5 px-3 font-semibold">Owner</th>
                <th className="text-left py-2.5 px-3 font-semibold">Priority</th>
                <th className="text-left py-2.5 px-3 font-semibold">Deadline</th>
                <th className="text-left py-2.5 px-3 font-semibold">Status</th>
                <th className="text-left py-2.5 px-3 pr-5 font-semibold">Meeting</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t, idx) => {
                const isDone = t.status === 'Done'
                return (
                  <tr
                    key={t.id || idx}
                    className={`border-b border-gray-50 transition-colors ${
                      isDone ? 'bg-gray-50/50 hover:bg-gray-100/50' : 'hover:bg-indigo-50/30'
                    }`}
                  >
                    <td className="py-3 px-5 max-w-[200px]">
                      <span
                        className={`block truncate font-medium ${isDone ? 'line-through text-gray-400' : 'text-gray-800'}`}
                        title={t.task_name}
                      >
                        {t.task_name}
                      </span>
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      <span className={`text-xs font-medium ${isDone ? 'text-gray-400' : 'text-gray-600'}`}>
                        {t.owner || '—'}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${isDone ? 'opacity-40' : ''} ${priorityBadge(t.priority)}`}>
                        {t.priority || '—'}
                      </span>
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      <span className={`text-xs ${isDone ? 'text-gray-400' : 'text-gray-500'}`}>
                        {fmtDate(t.deadline)}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${statusBadge(t.status)}`}>
                        {t.status || '—'}
                      </span>
                    </td>
                    <td className="py-3 px-3 pr-5 max-w-[160px]">
                      <span className="block truncate text-xs text-gray-400" title={t.meeting_summary || ''}>
                        {meetingTitle(t.meeting_summary)}
                      </span>
                    </td>
                  </tr>
                )
              })}
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

  const fmt = (iso) => iso
    ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '—'

  return (
    <div className="flex flex-col h-full">
      <div className="px-5 py-3 border-b border-gray-100 shrink-0 bg-white">
        <span className="text-sm font-semibold text-gray-700">
          {meetings.length} meeting{meetings.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="text-center py-12 text-gray-400 text-sm">Loading meetings…</div>
        ) : meetings.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 gap-2">
            <span className="text-4xl">📋</span>
            <p className="text-gray-500 font-medium text-sm">No meetings yet</p>
            <p className="text-gray-400 text-xs">Process a transcript to save a meeting</p>
          </div>
        ) : (
          <div className="space-y-2">
            {meetings.map(m => (
              <div key={m.meeting_id} className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
                <button
                  onClick={() => setExpanded(expanded === m.meeting_id ? null : m.meeting_id)}
                  className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-gray-50 text-left transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-gray-800 truncate">{m.title}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{fmt(m.created_at)}</p>
                  </div>
                  <svg
                    className={`w-4 h-4 text-gray-400 ml-3 shrink-0 transition-transform ${expanded === m.meeting_id ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                {expanded === m.meeting_id && (
                  <div className="px-4 pb-4 pt-3 text-sm text-gray-600 border-t border-gray-100 leading-relaxed bg-gray-50">
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

function StatCard({ label, value, sub, color, icon }) {
  return (
    <div className={`rounded-xl p-4 ${color}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-xs font-medium mt-0.5 opacity-80">{label}</p>
          {sub && <p className="text-xs opacity-60 mt-0.5">{sub}</p>}
        </div>
        <span className="text-xl opacity-60">{icon}</span>
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

  if (loading) return (
    <div className="flex items-center justify-center h-40 text-gray-400 text-sm gap-2">
      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
      Loading analytics…
    </div>
  )
  if (!data) return null

  const velocity    = data.velocity?.velocity  ?? data.velocity  ?? {}
  const owners      = data.ownership?.owners   ?? []
  const overdueList = data.overdue?.tasks      ?? []
  const topics      = (data.topics?.topics     ?? []).slice(0, 16)
  const openTasks   = Math.max(0, (velocity.total_tasks ?? 0) - (velocity.completed_tasks ?? 0))
  const completionPct = velocity.total_tasks
    ? Math.round((velocity.completed_tasks ?? 0) / velocity.total_tasks * 100)
    : 0

  return (
    <div className="flex flex-col h-full overflow-y-auto px-5 py-5 space-y-6 bg-gray-50">
      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard icon="📅" label="Meetings"    value={velocity.total_meetings ?? 0}  color="bg-white border border-gray-200 text-indigo-700 shadow-sm" />
        <StatCard icon="📌" label="Open Tasks"  value={openTasks}                     color="bg-white border border-gray-200 text-amber-700 shadow-sm" />
        <StatCard icon="⚠️" label="Overdue"     value={overdueList.length}            color="bg-white border border-gray-200 text-red-600 shadow-sm" />
        <StatCard icon="✅" label="Completion"  value={`${completionPct}%`}           color="bg-white border border-gray-200 text-emerald-700 shadow-sm" />
      </div>

      {/* Task Ownership */}
      {owners.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Task Ownership</h3>
          <div className="space-y-3">
            {owners.slice(0, 7).map((o, i) => {
              const maxTasks = owners[0]?.total_tasks || 1
              const pct = Math.round((o.total_tasks / maxTasks) * 100)
              const COLORS = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444']
              return (
                <div key={o.owner}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="font-semibold text-gray-700">{o.owner}</span>
                    <span className="text-gray-400">{o.total_tasks} tasks · <span className="text-emerald-600 font-medium">{o.completion_pct ?? 0}% done</span></span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }}
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
        <div className="bg-white rounded-xl border border-red-100 p-4 shadow-sm">
          <h3 className="text-xs font-bold text-red-500 uppercase tracking-wider mb-3">⚠️ Overdue Tasks</h3>
          <div className="space-y-2">
            {overdueList.slice(0, 5).map(t => (
              <div key={t.id} className="flex justify-between items-center bg-red-50 rounded-lg px-3 py-2.5">
                <span className="text-sm text-gray-700 truncate max-w-[55%] font-medium" title={t.task_name}>
                  {t.task_name}
                </span>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span className="text-xs text-gray-500">{t.owner || '?'}</span>
                  <span className="text-xs bg-red-100 text-red-700 font-semibold px-2 py-0.5 rounded-full">
                    {t.days_overdue}d late
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recurring Topics */}
      {topics.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Recurring Topics</h3>
          <div className="flex flex-wrap gap-2">
            {topics.map(t => (
              <span key={t.word} className="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-full text-xs font-medium">
                {t.word}
                <span className="text-indigo-400 ml-1.5">×{t.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Root App ───────────────────────────────────────────────

const TABS = [
  { id: 'tasks',     label: 'Tasks',    icon: '✅' },
  { id: 'meetings',  label: 'Meetings', icon: '📋' },
  { id: 'analytics', label: 'Analytics',icon: '📊' },
]

export default function App() {
  const [tab,            setTab]            = useState('tasks')
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const triggerRefresh = () => setRefreshTrigger(n => n + 1)

  return (
    <div className="h-screen flex overflow-hidden bg-gray-100 font-sans antialiased">
      {/* Left — Chat (42%) */}
      <div className="w-[42%] min-w-80 border-r border-gray-200 flex flex-col overflow-hidden shadow-md">
        <ChatPanel
          onTranscriptProcessed={triggerRefresh}
          onTaskUpdated={triggerRefresh}
        />
      </div>

      {/* Right — Dashboard (58%) */}
      <div className="flex-1 flex flex-col overflow-hidden bg-white">
        {/* Tab bar */}
        <div className="flex border-b border-gray-200 px-5 shrink-0 bg-white gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3.5 text-sm font-semibold border-b-2 transition-all flex items-center gap-1.5 ${
                tab === t.id
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-400 hover:text-gray-600 hover:border-gray-300'
              }`}
            >
              <span>{t.icon}</span>
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

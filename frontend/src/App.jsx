import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { marked } from 'marked'

// ── Owner avatar helpers ───────────────────────────────────
const AVATAR_COLORS = [
  'bg-indigo-500','bg-violet-500','bg-pink-500','bg-rose-500',
  'bg-amber-500','bg-emerald-500','bg-cyan-500','bg-blue-500',
]
function ownerColor(name) {
  if (!name) return 'bg-gray-400'
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}
function OwnerAvatar({ name, size = 'sm' }) {
  if (!name || name === '—') return <span className="text-xs text-gray-400">—</span>
  // Handle multi-owner like "Sarah, John, Alex" — show up to 2 avatars
  const owners = name.split(/[,/]/).map(s => s.trim()).filter(Boolean).slice(0, 2)
  const sz = size === 'sm' ? 'w-5 h-5 text-[10px]' : 'w-7 h-7 text-xs'
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {owners.map((o, i) => (
        <span key={i} className={`${sz} rounded-full ${ownerColor(o)} text-white font-bold flex items-center justify-center shrink-0`} title={o}>
          {o.slice(0,2).toUpperCase()}
        </span>
      ))}
      {owners.length === 1 && (
        <span className="text-xs text-gray-600 font-medium truncate max-w-[80px]">{owners[0]}</span>
      )}
    </div>
  )
}

marked.setOptions({ breaks: true, gfm: true })

// Render markdown and open all links in a new tab via post-processing
// (avoids marked v9 renderer API breaking changes)
const renderMd = (text) => {
  if (!text) return ''
  try {
    const html = marked.parse(String(text))
    // Inject target="_blank" on every anchor tag
    return html.replace(/<a\s+href=/gi, '<a target="_blank" rel="noopener noreferrer" href=')
  } catch {
    return String(text)
  }
}

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
  if (!val || val === 'TBD' || val === 'Not specified') return '—'
  const s = String(val)
  if (s.includes('-')) {
    const d = new Date(s)
    return isNaN(d) ? s : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }
  return s.replace(/^(By|Before|Week of|Before )\s*/i, '').slice(0, 18)
}

// Convert any deadline string to YYYY-MM-DD for <input type="date"> value,
// or '' if unparseable (which will show the placeholder).
const toISODate = (val) => {
  if (!val || val === 'TBD' || val === 'Not specified') return ''
  const s = String(val)
  // Already ISO
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const d = new Date(s)
  if (isNaN(d)) return ''
  return d.toISOString().slice(0, 10)
}

const meetingTitle = (summary) => {
  if (!summary) return '—'
  return summary.split('.')[0].replace(/^The /i, '').slice(0, 35)
}

// ── Meeting Briefing Parser + Card ────────────────────────────────────────────

function parseBriefing(text) {
  if (!text?.includes('✅ Meeting Processed Successfully')) return null

  const get = (pattern) => { const m = text.match(pattern); return m?.[1]?.trim() ?? null }

  // Summary block
  const summary = get(/📋 Summary:\n([\s\S]*?)(?=\n✅ Action Items:|\n💾 System Actions:|$)/)

  // Action items — each line: • Priority — Task — Owner: X — Due: Y
  const actionBlock = get(/✅ Action Items:\n([\s\S]*?)(?=\n💾 System Actions:|$)/)
  const actions = (actionBlock ?? '').split('\n')
    .filter(l => l.trim().startsWith('•'))
    .map(line => {
      const m = line.match(/^[•]\s*(High|Medium|Low)\s*[—–]\s*(.+?)\s*[—–]\s*Owner:\s*(.+?)\s*[—–]\s*Due:\s*(.+)$/i)
      if (m) return { priority: m[1], task: m[2].trim(), owner: m[3].trim(), due: m[4].trim() }
      // Fallback: just the raw line
      return { priority: null, task: line.replace(/^[•]\s*/, '').trim(), owner: null, due: null }
    })
    .filter(a => a.task)

  // System actions summary line (e.g. "3 tasks saved and 1 calendar event created.")
  const systemActions = get(/💾 System Actions:\n(.*?)(?:\n|$)/)

  // Calendar URL from markdown link or raw href
  const calUrl = text.match(/\[(?:Click here[^\]]*)\]\((https?:\/\/[^\)]+)\)/i)?.[1]
    ?? text.match(/https:\/\/calendar\.google\.com\/[^\s\)]+/)?.[0]
    ?? null

  // Google Doc URL
  const docUrl = text.match(/\[(?:view|open|here)[^\]]*\]\((https?:\/\/docs\.google\.com\/[^\)]+)\)/i)?.[1]
    ?? text.match(/https:\/\/docs\.google\.com\/document\/[^\s\)]+/)?.[0]
    ?? null

  // Pipeline descriptor
  const pipeline = get(/📊 Pipeline:\s*(.+)/)

  // "Try:" suggestion chips
  const trySuggestions = get(/✨ Try:\s*(.+)/)
    ?.split('·').map(s => s.replace(/^["']|["']$/g, '').trim()).filter(Boolean) ?? []

  // Meeting cost estimate
  // Count unique non-trivial owners as a proxy for attendees, then add ~30% buffer
  // for attendees who didn't take on tasks (observers, facilitators)
  const uniqueOwners = [...new Set(
    actions.map(a => a.owner).filter(o => o && o !== 'Unassigned' && o.length > 1)
  )]
  const attendeeCount = Math.max(2, Math.round(uniqueOwners.length * 1.3))
  // Loaded cost: 45-min meeting × $150/hr per person (includes salary + benefits + overhead)
  const meetingCostUSD = Math.round(attendeeCount * 0.75 * 150)

  return { summary, actions, systemActions, calUrl, docUrl, pipeline, trySuggestions, attendeeCount, meetingCostUSD }
}

const PRIORITY_STYLE = {
  High:   'bg-red-100 text-red-700 border border-red-200',
  Medium: 'bg-amber-100 text-amber-700 border border-amber-200',
  Low:    'bg-emerald-100 text-emerald-700 border border-emerald-200',
}

function MeetingBriefingCard({ text, onSuggest }) {
  const p = useMemo(() => parseBriefing(text), [text])
  const [summaryOpen, setSummaryOpen] = useState(false)
  if (!p) return null

  const highCount = p.actions.filter(a => a.priority === 'High').length
  const medCount  = p.actions.filter(a => a.priority === 'Medium').length

  return (
    <div className="space-y-2.5 text-sm w-full">

      {/* ── Header ── */}
      <div className="flex items-center gap-2">
        <span className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center text-xs shrink-0">✅</span>
        <span className="font-semibold text-emerald-700 text-sm">Meeting Processed Successfully</span>
        {p.actions.length > 0 && (
          <span className="ml-auto text-[10px] font-bold bg-emerald-50 text-emerald-600 border border-emerald-200 rounded-full px-2 py-0.5">
            {p.actions.length} tasks
          </span>
        )}
      </div>

      {/* ── Meeting cost ── */}
      {p.meetingCostUSD > 0 && (
        <div className="flex items-center gap-3 bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-100 rounded-xl px-3 py-2">
          <span className="text-base">💰</span>
          <div className="flex-1 min-w-0">
            <span className="text-xs font-bold text-amber-700">Est. meeting cost: </span>
            <span className="text-sm font-bold text-amber-800">${p.meetingCostUSD.toLocaleString()}</span>
            <span className="text-[10px] text-amber-500 ml-1">({p.attendeeCount} attendees × 45 min × $150/hr)</span>
          </div>
          <span className="text-[10px] text-amber-400 shrink-0 hidden sm:block">Catalyst saved this automatically</span>
        </div>
      )}

      {/* ── Summary ── */}
      {p.summary && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl overflow-hidden">
          <button
            onClick={() => setSummaryOpen(v => !v)}
            className="w-full flex items-center justify-between px-3 py-2 text-left"
          >
            <span className="text-[11px] font-bold text-indigo-600 uppercase tracking-wider">📋 Summary</span>
            <span className="text-[10px] text-indigo-400">{summaryOpen ? '▲ less' : '▼ more'}</span>
          </button>
          {summaryOpen && (
            <p className="px-3 pb-3 text-xs text-gray-700 leading-relaxed border-t border-indigo-100">{p.summary}</p>
          )}
        </div>
      )}

      {/* ── Action Items ── */}
      {p.actions.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
          <div className="px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center gap-2">
            <span className="text-[11px] font-bold text-gray-600 uppercase tracking-wider">Action Items</span>
            {highCount > 0 && <span className="text-[9px] font-bold bg-red-100 text-red-600 rounded-full px-1.5 py-0.5">{highCount} High</span>}
            {medCount  > 0 && <span className="text-[9px] font-bold bg-amber-100 text-amber-600 rounded-full px-1.5 py-0.5">{medCount} Med</span>}
          </div>
          <div className="divide-y divide-gray-50">
            {p.actions.map((a, i) => (
              <div key={i} className="flex items-start gap-2 px-3 py-2 hover:bg-gray-50/60 transition-colors">
                {a.priority
                  ? <span className={`shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded-full mt-0.5 ${PRIORITY_STYLE[a.priority] ?? 'bg-gray-100 text-gray-500'}`}>{a.priority}</span>
                  : <span className="shrink-0 text-gray-300 mt-1">•</span>
                }
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-gray-800 font-medium leading-snug">{a.task}</p>
                  <div className="flex flex-wrap gap-2 mt-0.5">
                    {a.owner && <span className="text-[10px] text-indigo-500">👤 {a.owner}</span>}
                    {a.due && a.due !== 'TBD' && <span className="text-[10px] text-gray-400">🗓 {a.due}</span>}
                    {a.due === 'TBD' && <span className="text-[10px] text-gray-400">🗓 TBD</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Footer chips ── */}
      <div className="flex flex-wrap gap-1.5">
        {p.systemActions && (
          <span className="text-[11px] bg-gray-100 text-gray-600 rounded-lg px-2 py-1">💾 {p.systemActions}</span>
        )}
        {p.calUrl && (
          <a href={p.calUrl} target="_blank" rel="noopener noreferrer"
            className="text-[11px] bg-blue-50 text-blue-700 border border-blue-100 rounded-lg px-2 py-1 hover:bg-blue-100 transition-colors font-medium">
            📅 Add to Calendar
          </a>
        )}
        {p.docUrl && (
          <a href={p.docUrl} target="_blank" rel="noopener noreferrer"
            className="text-[11px] bg-emerald-50 text-emerald-700 border border-emerald-100 rounded-lg px-2 py-1 hover:bg-emerald-100 transition-colors font-medium">
            📄 Open Doc
          </a>
        )}
      </div>

      {/* ── Pipeline info ── */}
      {p.pipeline && (
        <p className="text-[10px] text-gray-400 leading-relaxed">📊 {p.pipeline}</p>
      )}

      {/* ── Try suggestions ── */}
      {p.trySuggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {p.trySuggestions.map((s, i) => (
            <button
              key={i}
              onClick={() => onSuggest?.(s)}
              className="text-[11px] bg-indigo-50 text-indigo-600 border border-indigo-100 rounded-full px-2.5 py-0.5 hover:bg-indigo-100 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

    </div>
  )
}

// Detect if a message is a task-update command
const isTaskUpdate = (msg) =>
  /\b(mark|done|complete|in progress|update|finish|finished|status)\b/i.test(msg)

// Detect if agent response confirms a task was updated
const isTaskUpdateConfirm = (reply) =>
  /marked as|updated to|status.*changed|task.*done|task.*progress|task.*complete/i.test(reply)

// ── Pipeline Visualizer ────────────────────────────────────

const PIPELINE_STAGES = [
  { label: 'Analyse',      icon: '📝', parallel: false },
  { label: 'Save',         icon: '💾', parallel: false },
  { label: 'Notes ∥ Eval', icon: '⚡', parallel: true  },
]

function PipelineVisualizer({ currentStage, complete }) {
  return (
    <div className="w-full my-1">
      {/* Circles + connectors row */}
      <div className="flex items-center">
        {PIPELINE_STAGES.map((s, i) => {
          const done   = complete || i < currentStage
          const active = !complete && i === currentStage
          return (
            <div key={s.label} className="flex items-center flex-1">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-500 shrink-0 relative
                ${done   ? 'bg-emerald-500 text-white'
                : active ? 'bg-indigo-500 text-white animate-pulse'
                         : 'bg-gray-100 text-gray-400'}`}>
                {done ? '✓' : s.icon}
                {/* Parallel badge */}
                {s.parallel && active && (
                  <span className="absolute -top-1 -right-1 w-3 h-3 bg-violet-500 rounded-full flex items-center justify-center text-[7px] text-white font-black">∥</span>
                )}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 rounded transition-all duration-500
                  ${i < currentStage || complete ? 'bg-emerald-400' : 'bg-gray-100'}`} />
              )}
            </div>
          )
        })}
      </div>
      {/* Labels row */}
      <div className="flex mt-1.5">
        {PIPELINE_STAGES.map((s, i) => {
          const done   = complete || i < currentStage
          const active = !complete && i === currentStage
          return (
            <div key={s.label} className="flex-1 flex justify-start">
              <span className={`text-xs font-medium transition-colors duration-300 leading-tight
                ${done   ? 'text-emerald-600'
                : active ? s.parallel ? 'text-violet-600' : 'text-indigo-600'
                         : 'text-gray-300'}`}>
                {s.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Quality Scorecard ──────────────────────────────────────

function QualityScorecard({ score, onClose }) {
  const metrics = [
    { label: 'Summary',    value: score.summary_quality },
    { label: 'Tasks',      value: score.task_extraction_completeness },
    { label: 'Priorities', value: score.priority_accuracy },
    { label: 'Owners',     value: score.owner_attribution },
  ]
  const overall = score.overall_score ?? 0
  const color = overall >= 4 ? 'text-emerald-600' : overall >= 3 ? 'text-amber-600' : 'text-red-500'
  return (
    <div className="bg-gradient-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-xl p-4 mt-2 relative">
      <button onClick={onClose} className="absolute top-2 right-2 text-gray-400 hover:text-gray-600 text-xs leading-none">✕</button>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-base">🏅</span>
        <span className="text-sm font-bold text-indigo-700">Processing Quality</span>
        <span className={`ml-auto text-lg font-extrabold ${color}`}>{overall.toFixed(1)}<span className="text-xs font-normal text-gray-400">/5</span></span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {metrics.map(m => (
          <div key={m.label} className="bg-white rounded-lg p-2 text-center shadow-sm">
            <div className={`text-xl font-extrabold ${m.value >= 4 ? 'text-emerald-600' : m.value >= 3 ? 'text-amber-500' : 'text-red-500'}`}>
              {m.value ?? '—'}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">{m.label}</div>
            <div className="flex gap-0.5 mt-1.5 justify-center">
              {[1,2,3,4,5].map(n => (
                <div key={n} className={`w-1.5 h-1.5 rounded-full ${n <= (m.value ?? 0) ? 'bg-indigo-500' : 'bg-gray-200'}`} />
              ))}
            </div>
          </div>
        ))}
      </div>
      {score.flags?.length > 0 && (
        <p className="text-xs text-gray-500 mt-2 leading-relaxed">
          💬 {score.flags[0]}
        </p>
      )}
    </div>
  )
}

// ── Chat Panel ─────────────────────────────────────────────

const DEMO_TRANSCRIPT = `Meeting Title: Q3 Product Planning Discussion
Date: June 5, 2026
Attendees: Sarah (Product Manager), John (Engineering Lead), Maria (Design Lead), Alex (Marketing)

Sarah: Good morning everyone. Let's dive into our Q3 roadmap. Our main priority is launching the mobile app by end of August. John, can you give us a status update on the backend infrastructure?

John: Sure. The API is 80% complete. We need to finish the authentication module and optimize the database queries. I estimate we need another 3 weeks. I'll assign Tom to handle the auth module since he has experience with OAuth implementations.

Sarah: Great. Make sure the authentication is rock solid - security is critical for mobile. Maria, how's the UI design coming along?

Maria: We've completed wireframes for all core screens. The design system is finalized. My team is now working on high-fidelity mockups. We should have everything ready for handoff to engineering by June 20th. I need Alex's team to provide the final copy for onboarding screens though.

Alex: No problem. I'll get the copywriting done by next week. We're also planning a launch campaign for August 25th. We need beta testers lined up by July 15th to get feedback before the public launch. Sarah, can you coordinate the beta program?

Sarah: Yes, I'll own the beta program. I'll need John to set up a separate staging environment for beta users by July 1st. Also, we need to fix the notification system bugs that came up last sprint - customers are complaining about delayed push notifications.

John: I saw those bug reports. I'll prioritize the notification fix. It's probably related to our queue processing. I'll assign Lisa to investigate this week and we should have a fix deployed by end of next week.

Maria: One more thing - we need to schedule a design review meeting with stakeholders before we start development. Can we do that on June 15th at 10 AM?

Sarah: June 15th works for me. Let's make it happen. John and Alex, please block your calendars. Any other blockers before we wrap up?

John: We need budget approval for two additional cloud servers to handle beta load. I'll send a request to finance today.

Alex: I'll coordinate with PR for the launch announcement. We should aim for tech blog coverage too.

Sarah: Great. Let's reconvene next week with updates. Meeting adjourned.`

const WELCOME = '⚡ **Welcome to Catalyst!**\n*Raw meetings. Structured action.*\n\nI\'m powered by **8 specialized agents** and **4 MCP servers** working together.\n\n**Try:**\n- Paste any meeting transcript (500+ chars)\n- "What tasks are pending?"\n- "Who has the most tasks?"\n- "What\'s overdue?"'

const MESSAGES_KEY = 'mm_messages'
const MESSAGES_VERSION = 'catalyst_v2'   // bump this to flush stale localStorage on deploy

// ── Speech Recognition hook ────────────────────────────────
// ── Toast notification ─────────────────────────────────────
function Toast({ message, onDone }) {
  useEffect(() => {
    const t = setTimeout(onDone, 3000)
    return () => clearTimeout(t)
  }, [onDone])
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 px-4 py-2.5 bg-gray-800 text-white text-xs font-medium rounded-full shadow-xl flex items-center gap-2" style={{ animation: 'fadeInUp .25s ease' }}>
      <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse shrink-0" />
      {message}
    </div>
  )
}

function useSpeechRecognition({ onFinalText, onInterim, onToast }) {
  const recRef   = useRef(null)
  const timerRef = useRef(null)
  const [isRecording, setIsRecording] = useState(false)
  const [duration,    setDuration]    = useState(0)
  const [supported,   setSupported]   = useState(
    () => !!(window.SpeechRecognition || window.webkitSpeechRecognition)
  )

  useEffect(() => {
    setSupported(!!(window.SpeechRecognition || window.webkitSpeechRecognition))
  }, [])

  const start = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    const rec = new SR()
    rec.continuous      = true
    rec.interimResults  = true
    rec.lang            = 'en-US'
    rec.maxAlternatives = 1

    rec.onresult = (e) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript
        if (e.results[i].isFinal) {
          onFinalText(t.trim() + ' ')
        } else {
          interim += t
        }
      }
      onInterim(interim)
    }
    rec.onerror = (e) => {
      if (e.error !== 'no-speech') stop()
    }
    rec.onend = () => {
      // Auto-restart if still recording (browser cuts off after ~60s)
      if (recRef.current) {
        try {
          recRef.current.start()
          onToast?.('🎙 Mic restarted — browser 60s limit reached, continuing…')
        } catch {}
      }
    }

    recRef.current = rec
    rec.start()
    setIsRecording(true)
    setDuration(0)
    timerRef.current = setInterval(() => setDuration(d => d + 1), 1000)
  }, [onFinalText, onInterim, onToast])

  const stop = useCallback(() => {
    if (recRef.current) {
      recRef.current.onend = null  // prevent auto-restart
      recRef.current.stop()
      recRef.current = null
    }
    clearInterval(timerRef.current)
    setIsRecording(false)
    setDuration(0)
  }, [])

  return { isRecording, duration, supported, start, stop }
}

function fmtDuration(s) {
  const m = Math.floor(s / 60), sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// ── Relative timestamp ─────────────────────────────────────
function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor((Date.now() - new Date(ts)) / 1000)
  if (diff < 10)  return 'just now'
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function ChatPanel({ onTranscriptProcessed, onTaskUpdated }) {
  const [messages, setMessages] = useState(() => {
    try {
      // Flush stale messages when the app version changes (e.g. MeetingMind → Catalyst rename)
      const storedVersion = localStorage.getItem('mm_version')
      if (storedVersion !== MESSAGES_VERSION) {
        localStorage.removeItem(MESSAGES_KEY)
        localStorage.setItem('mm_version', MESSAGES_VERSION)
        return [{ role: 'assistant', text: WELCOME, ts: Date.now() }]
      }
      const saved = localStorage.getItem(MESSAGES_KEY)
      return saved ? JSON.parse(saved) : [{ role: 'assistant', text: WELCOME, ts: Date.now() }]
    } catch { return [{ role: 'assistant', text: WELCOME, ts: Date.now() }] }
  })
  const [input,         setInput]         = useState('')
  const [loading,       setLoading]       = useState(false)
  const [pipelineStage, setPipelineStage] = useState(-1)  // -1 = not active
  const [isTranscript,  setIsTranscript]  = useState(false)
  const [interimText,   setInterimText]   = useState('')
  const [toast,         setToast]         = useState(null)
  const [sessionId]                       = useState(() => {
    const k = 'mm_sid'
    return localStorage.getItem(k) || (() => {
      const id = crypto.randomUUID()
      localStorage.setItem(k, id)
      return id
    })()
  })
  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)

  const onFinalText = useCallback((text) => {
    setInput(prev => prev + text)
    setInterimText('')
  }, [])

  const { isRecording, duration, supported, start: startMic, stop: stopMic } =
    useSpeechRecognition({ onFinalText, onInterim: setInterimText, onToast: setToast })

  const toggleMic = () => {
    if (isRecording) {
      stopMic()
      setInterimText('')
    } else {
      startMic()
    }
  }

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    try { localStorage.setItem(MESSAGES_KEY, JSON.stringify(messages.slice(-100))) } catch {}
  }, [messages])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Cmd+K / Ctrl+K — focus chat input from anywhere
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const send = async (overrideMsg) => {
    const msg = (overrideMsg ?? input).trim()
    if (!msg || loading) return
    if (!overrideMsg) setInput('')
    setMessages(m => [...m, { role: 'user', text: msg, ts: Date.now() }])
    setLoading(true)
    const wasTaskCommand  = isTaskUpdate(msg)
    const msgIsTranscript = msg.length > 400
    setIsTranscript(msgIsTranscript)
    setPipelineStage(msgIsTranscript ? 0 : -1)


    try {
      let recurringTopics = []
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

      // Read SSE stream — heartbeat lines keep connection alive, stage/response events carry data
      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let reply  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'heartbeat') continue
            if (evt.type === 'error') throw new Error(evt.detail || 'Agent error')
            if (evt.type === 'stage') setPipelineStage(evt.index)
            if (evt.type === 'duplicate') {
              setMessages(m => [...m, { role: 'duplicate', data: evt, ts: Date.now() }])
              setLoading(false)
              setPipelineStage(-1)
              setIsTranscript(false)
              return
            }
            if (evt.type === 'response') {
              reply = evt.response || '⚠️ No response.'
              if (evt.recurring_topics?.length) recurringTopics = evt.recurring_topics
            }
          } catch (parseErr) {
            if (parseErr.message !== 'Agent error' && !parseErr.message.startsWith('Agent')) continue
            throw parseErr
          }
        }
      }

      if (!reply) reply = '⚠️ No response received from agents.'

      const isProcessed = reply.includes('Meeting Processed') || reply.includes('meeting processed')

      if (isProcessed) {
        reply += '\n\n📄 Google Doc saved — view it in the **Docs** tab'
      }

      setMessages(m => [...m, { role: 'assistant', text: reply, ts: Date.now() }])

      if (recurringTopics.length > 0) {
        setMessages(m => [...m, { role: 'recurring', topics: recurringTopics, ts: Date.now() }])
      }

      if (isProcessed) {
        onTranscriptProcessed?.()
        // Fetch quality score — evaluation_agent runs in parallel with notes_agent (~5-6s)
        // No LLM calls — just a DB read each time. Retry at 3s and 6s, then give up silently.
        ;(async () => {
          for (const delay of [3000, 6000]) {
            await new Promise(r => setTimeout(r, delay))
            try {
              const q = await fetch('/api/quality').then(r => r.json())
              const latest = (q?.quality_scores ?? [])[0] ?? null
              if (latest?.overall_score != null) {
                setMessages(m => [...m, { role: 'quality', data: latest, ts: Date.now() }])
                return   // got it — stop
              }
            } catch {}
          }
          // Silent give-up after 6s total — scorecard simply doesn't appear
        })()
      } else if (wasTaskCommand && isTaskUpdateConfirm(reply)) {
        onTaskUpdated?.()
      }
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', text: `⚠️ ${e.message}`, ts: Date.now() }])
    } finally {
      setLoading(false)
      setPipelineStage(-1)
      setIsTranscript(false)
    }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <>
    {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-indigo-600 to-indigo-500 text-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight">⚡ Catalyst</span>
          <span className="text-xs bg-white/20 backdrop-blur px-2.5 py-0.5 rounded-full font-medium">8 Agents</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => send(DEMO_TRANSCRIPT)}
            disabled={loading}
            className="text-xs bg-white/20 hover:bg-white/30 backdrop-blur px-2.5 py-1 rounded-full font-medium transition-colors disabled:opacity-40"
            title="Auto-process a sample transcript through the full pipeline"
          >
            ▶ Try Demo
          </button>
          <span className="text-xs text-indigo-200 font-medium">Raw meetings. Structured action.</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4 bg-gray-50">
        {messages.map((m, i) => {
          // Duplicate meeting blocked card
          if (m.role === 'duplicate') {
            const d = m.data || {}
            return (
              <div key={i} className="flex justify-start items-start gap-2">
                <div className="w-7 h-7 rounded-full bg-red-100 flex items-center justify-center text-sm mr-0 mt-0.5 shrink-0">🚫</div>
                <div className="max-w-[92%] min-w-0 bg-red-50 border border-red-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
                  <p className="text-xs font-bold text-red-700 uppercase tracking-wider mb-1">
                    Duplicate Meeting Blocked
                  </p>
                  <p className="text-sm text-red-600 mb-3">
                    This transcript is <span className="font-bold">{d.similarity}% identical</span> to a meeting already processed on <span className="font-semibold">{d.original_date}</span>. Skipped save, calendar event, and doc creation.
                  </p>
                  {d.original_snippet && (
                    <div className="bg-white border border-red-100 rounded-lg px-3 py-2 mb-2">
                      <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Original meeting</p>
                      <p className="text-xs text-gray-600 leading-snug">{d.original_snippet}</p>
                    </div>
                  )}
                  <p className="text-[10px] text-red-400 italic">duplicates_blocked counter incremented · pgvector similarity ≥ 92%</p>
                </div>
              </div>
            )
          }

          // Recurring topic alert — cross-meeting RAG result
          if (m.role === 'recurring') {
            return (
              <div key={i} className="flex justify-start items-start gap-2">
                <div className="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center text-sm mr-0 mt-0.5 shrink-0">⚠️</div>
                <div className="max-w-[92%] min-w-0 bg-amber-50 border border-amber-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
                  <p className="text-xs font-bold text-amber-700 uppercase tracking-wider mb-2">
                    Recurring Topic Detected
                  </p>
                  <p className="text-xs text-amber-600 mb-3">
                    This topic appeared in {m.topics.length} previous meeting{m.topics.length > 1 ? 's' : ''} — it may be an unresolved systemic issue.
                  </p>
                  <div className="space-y-2">
                    {m.topics.map((t, ti) => (
                      <div key={ti} className="bg-white border border-amber-100 rounded-lg px-3 py-2">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider">{t.created_at}</span>
                          <span className="text-[10px] font-bold text-amber-600 bg-amber-100 rounded-full px-2 py-0.5">{t.similarity}% match</span>
                        </div>
                        <p className="text-xs text-gray-600 leading-snug">{t.summary_snippet}</p>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-amber-400 mt-2 italic">Powered by pgvector semantic search</p>
                </div>
              </div>
            )
          }

          // Quality scorecard message type
          if (m.role === 'quality') {
            return (
              <div key={i} className="flex justify-start items-start gap-2">
                <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm mr-0 mt-0.5 shrink-0">🏅</div>
                <div className="max-w-[90%] min-w-0">
                  <QualityScorecard
                    score={m.data}
                    onClose={() => setMessages(prev => prev.filter((_, idx) => idx !== i))}
                  />
                </div>
              </div>
            )
          }
          return (
            <div key={i} className={`flex flex-col min-w-0 ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`flex min-w-0 w-full ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm mr-2 mt-0.5 shrink-0">⚡</div>
                )}
                {(() => {
                  let isBriefing = false
                  try { isBriefing = !!parseBriefing(m.text) } catch {}
                  return (
                    <div className={`min-w-0 rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                      m.role === 'user'
                        ? 'max-w-[85%] bg-indigo-600 text-white rounded-br-none'
                        : isBriefing
                          ? 'w-full max-w-[92%] bg-white text-gray-800 rounded-bl-none border border-gray-100'
                          : 'max-w-[85%] bg-white text-gray-800 rounded-bl-none border border-gray-100'
                    }`} style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                      {m.role === 'assistant' ? (
                        isBriefing
                          ? <MeetingBriefingCard text={m.text} onSuggest={(s) => { setInput(s) }} />
                          : <div
                              className="prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-pre:overflow-x-auto prose-pre:whitespace-pre-wrap"
                              style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}
                              dangerouslySetInnerHTML={{ __html: renderMd(m.text) }}
                            />
                      ) : (
                        <span style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{m.text}</span>
                      )}
                    </div>
                  )
                })()}
              </div>
              {m.ts && (
                <span className={`text-[10px] text-gray-400 mt-0.5 ${m.role === 'user' ? 'pr-1' : 'pl-9'}`}>
                  {timeAgo(m.ts)}
                </span>
              )}
            </div>
          )
        })}

        {loading && (
          <div className="flex justify-start items-start gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm shrink-0">⚡</div>
            <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm min-w-[260px]">
              <p className="text-xs text-gray-500 mb-3 flex items-center gap-1.5 font-medium">
                <span className={pipelineStage >= PIPELINE_STAGES.length ? 'inline-block' : 'animate-spin inline-block'}>⚙️</span>
                {isTranscript
                  ? pipelineStage >= PIPELINE_STAGES.length ? 'Pipeline complete — assembling briefing…' : 'Pipeline running…'
                  : 'Agents working…'}
              </p>
              {isTranscript ? (
                <PipelineVisualizer currentStage={pipelineStage} complete={pipelineStage >= PIPELINE_STAGES.length} />
              ) : (
                <div className="flex gap-1.5">
                  {['Thinking', 'Querying', 'Writing'].map((s, i) => (
                    <span key={s} className="text-xs bg-indigo-50 text-indigo-600 px-2.5 py-1 rounded-full animate-pulse font-medium"
                      style={{ animationDelay: `${i * 0.3}s` }}>{s}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Suggested queries — only shown when input is empty and not loading */}
      {!input && !loading && (
        <div className="px-4 pt-3 flex flex-wrap gap-1.5">
          {[
            { label: '📋 Pending tasks',         query: 'What tasks are pending?' },
            { label: '🔴 High priority',          query: 'Show me all high priority tasks' },
            { label: '⏰ Overdue',                query: 'What tasks are overdue?' },
            { label: '🔍 Semantic search',        query: 'Find tasks similar to budget approval' },
            { label: '📅 Recent meetings',        query: 'List recent meetings' },
            { label: '👤 Tasks by owner',         query: 'Show task ownership breakdown' },
            { label: '💡 Remember preference',    query: 'Remember that our team prefers morning meetings' },
          ].map(({ label, query }) => (
            <button
              key={label}
              onClick={() => { setInput(query); }}
              className="text-xs px-2.5 py-1 rounded-full border border-gray-200 text-gray-500 hover:border-indigo-400 hover:text-indigo-600 hover:bg-indigo-50 transition-all whitespace-nowrap"
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-200 bg-white shrink-0">
        {/* Live mic preview */}
        {isRecording && (
          <div className="mb-2 px-3 py-2 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse shrink-0" />
            <span className="text-xs text-red-600 font-medium shrink-0">{fmtDuration(duration)}</span>
            <span className="text-xs text-red-500 italic truncate flex-1 min-w-0">
              {interimText || 'Listening…'}
            </span>
            <span className="text-xs text-red-400 shrink-0">Speak clearly</span>
          </div>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            className={`flex-1 resize-none border rounded-xl px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 transition-all placeholder-gray-400 ${
              isRecording
                ? 'border-red-300 focus:border-red-400 focus:ring-red-50 bg-red-50/30'
                : 'border-gray-200 focus:border-indigo-400 focus:ring-indigo-50 bg-gray-50'
            }`}
            rows={2}
            placeholder={isRecording ? '🎙 Recording… speak naturally — names, tasks, deadlines' : 'Paste a transcript, ask a question, or 🎙 record a live meeting…'}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={loading}
          />
          <div className="flex flex-col gap-1.5 shrink-0">
            {/* Mic button */}
            {supported && (
              <div className="flex flex-col items-center gap-0.5">
                <button
                  onClick={toggleMic}
                  disabled={loading}
                  title={isRecording ? 'Stop recording' : 'Speak your meeting aloud — Catalyst will process it live'}
                  className={`relative p-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm disabled:opacity-40 disabled:cursor-not-allowed ${
                    isRecording
                      ? 'bg-red-500 hover:bg-red-600 text-white ring-2 ring-red-300 ring-offset-1'
                      : 'bg-violet-100 hover:bg-violet-200 text-violet-600 ring-1 ring-violet-200'
                  }`}
                >
                  {/* Pulse ring when idle */}
                  {!isRecording && !loading && (
                    <span className="absolute inset-0 rounded-xl ring-2 ring-violet-400 animate-ping opacity-30 pointer-events-none" />
                  )}
                  {isRecording ? (
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                      <rect x="6" y="6" width="12" height="12" rx="2"/>
                    </svg>
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
                      <path strokeLinecap="round" strokeLinejoin="round"
                        d="M19 10v2a7 7 0 01-14 0v-2M12 19v4M8 23h8"/>
                    </svg>
                  )}
                </button>
                <span className={`text-[9px] font-semibold tracking-tight text-center leading-tight ${isRecording ? 'text-red-500' : 'text-violet-500'}`}>
                  {isRecording ? 'Stop' : 'Live'}
                </span>
              </div>
            )}
            {/* Send button */}
            <button
              onClick={() => send()}
              disabled={loading || !input.trim()}
              className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              Send
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between mt-1.5 pl-1">
          <p className="text-xs text-gray-400">
            {isRecording
              ? '🔴 Recording live — click ■ to stop, then Send to process'
              : <span>
                  {supported && <span className="mr-1">🎙 record ·</span>}
                  Enter to send · Shift+Enter newline · <kbd className="px-1 py-0.5 bg-gray-100 rounded text-[10px] font-mono text-gray-500">⌘K</kbd> focus
                </span>
            }
          </p>
          {input.length > 0 && (
            <span className={`text-[10px] font-medium tabular-nums transition-colors ${
              input.length >= 500 ? 'text-emerald-600 font-semibold' : 'text-gray-400'
            }`}>
              {input.length}{input.length >= 500 ? ' ✓ transcript detected' : ' / 500'}
            </span>
          )}
        </div>
      </div>
    </div>
    </>
  )
}

// ── Task Board ─────────────────────────────────────────────

const PRIORITY_ORDER = { High: 0, Medium: 1, Low: 2 }

// ── Task Detail Modal ──────────────────────────────────────
function TaskDetailModal({ task, onClose, onStatusChange, onDeadlineChange }) {
  if (!task) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg p-6 space-y-4"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-base font-bold text-gray-800 leading-snug flex-1">{task.task_name}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none shrink-0">×</button>
        </div>

        {/* Meta grid */}
        <div className="grid grid-cols-2 gap-3">
          {/* Owner */}
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-xs text-gray-400 font-medium mb-0.5">Owner</p>
            <p className="text-sm font-semibold text-gray-700">{task.owner || '—'}</p>
          </div>
          {/* Deadline — editable date input */}
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-xs text-gray-400 font-medium mb-1">Deadline</p>
            <input
              type="date"
              defaultValue={toISODate(task.deadline)}
              onChange={e => onDeadlineChange?.(task, e.target.value)}
              className="text-sm font-semibold text-gray-700 bg-transparent w-full focus:outline-none focus:ring-2 focus:ring-indigo-300 rounded-lg px-1 -mx-1 cursor-pointer"
            />
            {task.deadline && task.deadline !== 'TBD' && task.deadline !== 'Not specified' && (
              <p className="text-xs text-gray-400 mt-0.5">{task.deadline}</p>
            )}
          </div>
          {/* Priority */}
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-xs text-gray-400 font-medium mb-0.5">Priority</p>
            <p className="text-sm font-semibold text-gray-700">{task.priority || '—'}</p>
          </div>
          {/* Meeting */}
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-xs text-gray-400 font-medium mb-0.5">Meeting</p>
            <p className="text-sm font-semibold text-gray-700 leading-snug" style={{ overflowWrap:'anywhere' }}>
              {task.meeting_summary ? task.meeting_summary.slice(0, 60) + '…' : '—'}
            </p>
          </div>
        </div>

        {/* Status change */}
        <div>
          <p className="text-xs text-gray-400 font-medium mb-2">Update Status</p>
          <div className="flex gap-2 flex-wrap">
            {['Pending','In Progress','Done','Cancelled'].map(s => (
              <button
                key={s}
                onClick={() => { onStatusChange(task, s); onClose() }}
                className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-all hover:shadow-sm ${
                  task.status === s
                    ? 'ring-2 ring-indigo-400 ring-offset-1 ' + statusBadge(s)
                    : statusBadge(s) + ' opacity-60 hover:opacity-100'
                }`}
              >
                {task.status === s ? '✓ ' : ''}{s}
              </button>
            ))}
          </div>
        </div>

        {/* Close */}
        <button
          onClick={onClose}
          className="w-full py-2 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-xl transition-colors"
        >
          Close
        </button>
      </div>
    </div>
  )
}

// ── CSV export helper ──────────────────────────────────────
function exportTasksCSV(tasks, label = 'all-tasks') {
  const headers = ['Task','Owner','Priority','Deadline','Status','Meeting']
  const rows = tasks.map(t => [
    `"${(t.task_name  || '').replace(/"/g, '""')}"`,
    `"${(t.owner      || '').replace(/"/g, '""')}"`,
    `"${(t.priority || '').replace(/"/g, '""')}"`,
    `"${(t.deadline || '').replace(/"/g, '""')}"`,
    `"${(t.status   || '').replace(/"/g, '""')}"`,
    `"${(t.meeting_summary || '').slice(0, 80).replace(/"/g, '""')}"`,
  ])
  const csv  = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
  const date = new Date().toISOString().slice(0, 10)
  const blob = new Blob([csv], { type: 'text/csv' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `catalyst-${slug}-${date}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function TaskBoard({ refreshTrigger, ownerFilter, onClearOwner, statusFilter, onClearStatus, onCountsChange }) {
  const [tasks,      setTasks]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [filter,     setFilter]     = useState(statusFilter ?? 'all')
  const [search,     setSearch]     = useState('')
  const [sortBy,     setSortBy]     = useState('priority') // 'priority' | 'deadline'
  const [detailTask, setDetailTask] = useState(null)       // task detail modal
  const [selected,   setSelected]   = useState(new Set())  // bulk select
  const [flashId,    setFlashId]    = useState(null)       // row flash after status change

  // Sync external statusFilter (e.g. from Analytics nav)
  useEffect(() => {
    if (statusFilter && statusFilter !== filter) setFilter(statusFilter)
  }, [statusFilter])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (ownerFilter) params.set('owner', ownerFilter)
      const res = await fetch(`/api/tasks${params.toString() ? '?' + params : ''}`)
      const d   = await res.json()
      setTasks(d.tasks || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [ownerFilter])

  useEffect(() => { load() }, [load, refreshTrigger])

  const today = new Date(); today.setHours(0,0,0,0)
  const isOverdue = (t) => {
    if (t.status === 'Done' || t.status === 'Cancelled') return false
    if (!t.deadline || t.deadline === 'Not specified' || t.deadline === 'TBD') return false
    const d = new Date(t.deadline)
    return !isNaN(d) && d < today
  }

  // Propagate live counts to App whenever tasks change (inline edits, bulk actions, etc.)
  // This keeps the tab badge accurate without a full re-fetch.
  useEffect(() => {
    if (!onCountsChange || loading) return
    const openCount   = tasks.filter(t => t.status === 'Pending' || t.status === 'In Progress').length
    const overdueCount = tasks.filter(isOverdue).length
    onCountsChange({ tasks: openCount, overdue: overdueCount })
  }, [tasks, loading])  // eslint-disable-line react-hooks/exhaustive-deps

  const filters = [
    { id: 'all',         label: 'All' },
    { id: 'Pending',     label: 'Pending' },
    { id: 'In Progress', label: 'In Progress' },
    { id: 'Done',        label: 'Done' },
    { id: 'Cancelled',   label: 'Cancelled' },
    { id: 'Overdue',     label: '⏰ Overdue' },
  ]

  const counts = {
    all:          tasks.length,
    Pending:      tasks.filter(t => t.status === 'Pending').length,
    'In Progress':tasks.filter(t => t.status === 'In Progress').length,
    Done:         tasks.filter(t => t.status === 'Done').length,
    Cancelled:    tasks.filter(t => t.status === 'Cancelled').length,
    Overdue:      tasks.filter(isOverdue).length,
  }

  const q = search.trim().toLowerCase()
  const visible = tasks
    .filter(t => {
      if (filter === 'all')     return true
      if (filter === 'Overdue') return isOverdue(t)
      return t.status === filter
    })
    .filter(t => !q || t.task_name?.toLowerCase().includes(q) || t.owner?.toLowerCase().includes(q))
    .sort((a, b) => {
      if (sortBy === 'priority') return (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3)
      // deadline sort — push missing deadlines to end
      const da = a.deadline && a.deadline !== 'Not specified' ? a.deadline : 'zzz'
      const db = b.deadline && b.deadline !== 'Not specified' ? b.deadline : 'zzz'
      return da.localeCompare(db)
    })

  const handleModalStatusChange = async (task, newStatus) => {
    setTasks(prev => prev.map(x => x.id === task.id ? { ...x, status: newStatus } : x))
    try {
      await fetch(`/api/tasks/${task.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
    } catch { load() }
  }

  const handleModalDeadlineChange = async (task, newDate) => {
    // Optimistic update — also update detailTask so the modal reflects the new value
    setTasks(prev => prev.map(x => x.id === task.id ? { ...x, deadline: newDate || 'Not specified' } : x))
    setDetailTask(prev => prev ? { ...prev, deadline: newDate || 'Not specified' } : prev)
    try {
      await fetch(`/api/tasks/${task.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ deadline: newDate || '' }),
      })
    } catch { load() }
  }

  return (
    <>
    {detailTask && (
      <TaskDetailModal
        task={detailTask}
        onClose={() => setDetailTask(null)}
        onStatusChange={handleModalStatusChange}
        onDeadlineChange={handleModalDeadlineChange}
      />
    )}
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-gray-100 bg-white shrink-0 space-y-2">
        {/* Row 1: status filters + refresh + export */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 flex-wrap">
            {ownerFilter && (
              <span className="flex items-center gap-1 px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-lg text-xs font-semibold">
                👤 {ownerFilter}
                <button onClick={onClearOwner} className="ml-1 hover:text-indigo-900 font-bold">×</button>
              </span>
            )}
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
                  {f.id === 'all' ? counts.all : counts[f.id] ?? 0}
                </span>
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {/* CSV Export */}
            <button
              onClick={() => {
                const parts = []
                if (filter && filter !== 'all') parts.push(filter.toLowerCase().replace(' ', '-'))
                else parts.push('all-tasks')
                if (ownerFilter) parts.push(ownerFilter.toLowerCase().replace(/\s+/g, '-'))
                if (search.trim()) parts.push('search-' + search.trim().toLowerCase().replace(/\s+/g, '-').slice(0, 20))
                exportTasksCSV(visible, parts.join('-'))
              }}
              title="Export visible tasks to CSV"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:text-emerald-700 hover:bg-emerald-50 border border-gray-200 hover:border-emerald-200 transition-all"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
              </svg>
              CSV
            </button>
            {/* Refresh */}
            <button onClick={load} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors" title="Refresh">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>
        {/* Row 2: search + sort */}
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search tasks or owner…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 bg-gray-50 placeholder-gray-400"
          />
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-xs text-gray-400">Sort:</span>
            {['priority', 'deadline'].map(s => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-all capitalize ${
                  sortBy === s ? 'bg-indigo-100 text-indigo-700' : 'text-gray-400 hover:text-gray-600'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
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
          <div className="flex flex-col items-center justify-center h-48 text-center gap-2 px-8">
            <span className="text-4xl">📋</span>
            <p className="text-gray-500 font-medium text-sm">No tasks yet</p>
            <p className="text-gray-400 text-xs">Paste a meeting transcript in the chat — Catalyst will extract and prioritise action items automatically.</p>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center gap-2">
            <span className="text-2xl">🔍</span>
            <p className="text-gray-400 text-xs">No tasks match "{search}"</p>
          </div>
        ) : (
          <>{selected.size > 0 && (
            <div className="sticky top-0 z-20 flex items-center gap-2 px-5 py-2 bg-indigo-50 border-b border-indigo-200">
              <span className="text-xs font-semibold text-indigo-700">{selected.size} selected</span>
              <button
                onClick={async () => {
                  const ids = [...selected]
                  // Optimistic UI update
                  setTasks(prev => prev.map(t => ids.includes(t.id) ? { ...t, status: 'Done' } : t))
                  setSelected(new Set())
                  // Persist to DB — all in parallel
                  const results = await Promise.all(ids.map(id =>
                    fetch(`/api/tasks/${id}`, {
                      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ status: 'Done' }),
                    }).then(r => r.ok ? 'ok' : 'fail').catch(() => 'fail')
                  ))
                  // If any failed, reload from DB to restore true state
                  if (results.includes('fail')) load()
                }}
                className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
              >✓ Mark Done</button>
              <button
                onClick={async () => {
                  const ids = [...selected]
                  // Optimistic UI update
                  setTasks(prev => prev.map(t => ids.includes(t.id) ? { ...t, status: 'Cancelled' } : t))
                  setSelected(new Set())
                  // Persist to DB — all in parallel
                  const results = await Promise.all(ids.map(id =>
                    fetch(`/api/tasks/${id}`, {
                      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ status: 'Cancelled' }),
                    }).then(r => r.ok ? 'ok' : 'fail').catch(() => 'fail')
                  ))
                  // If any failed, reload from DB to restore true state
                  if (results.includes('fail')) load()
                }}
                className="px-2.5 py-1 rounded-full text-xs font-semibold bg-gray-500 text-white hover:bg-gray-600 transition-colors"
              >✕ Cancel</button>
              <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-indigo-400 hover:text-indigo-700">Clear</button>
            </div>
          )}
          <table className="w-full text-sm border-collapse">
            <thead className="sticky top-0 bg-gray-50 z-10">
              <tr className="text-xs uppercase text-gray-400 border-b border-gray-200">
                <th className="py-2.5 px-3 w-8">
                  <input type="checkbox"
                    className="rounded cursor-pointer accent-indigo-600"
                    checked={visible.length > 0 && visible.every(t => selected.has(t.id))}
                    onChange={e => setSelected(e.target.checked ? new Set(visible.map(t => t.id)) : new Set())}
                  />
                </th>
                <th className="text-left py-2.5 px-2 font-semibold">Task</th>
                <th className="text-left py-2.5 px-3 font-semibold">Owner</th>
                <th className="text-left py-2.5 px-3 font-semibold">Priority</th>
                <th className="text-left py-2.5 px-3 font-semibold">Deadline</th>
                <th className="text-left py-2.5 px-3 font-semibold">Status</th>
                <th className="text-left py-2.5 px-3 pr-5 font-semibold">Meeting</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t, idx) => {
                const isDone = t.status === 'Done' || t.status === 'Cancelled'
                return (
                  <tr
                    key={t.id || idx}
                    onClick={() => setDetailTask(t)}
                    className={`border-b border-gray-50 transition-all duration-500 cursor-pointer ${
                      flashId === t.id ? 'bg-emerald-50' : selected.has(t.id) ? 'bg-indigo-50/60' : isDone ? 'bg-gray-50/50 hover:bg-gray-100/50' : 'hover:bg-indigo-50/40'
                    }`}
                  >
                    <td className="py-3 px-3 w-8" onClick={e => { e.stopPropagation(); setSelected(prev => { const n = new Set(prev); n.has(t.id) ? n.delete(t.id) : n.add(t.id); return n }) }}>
                      <input type="checkbox" className="rounded cursor-pointer accent-indigo-600"
                        checked={selected.has(t.id)} onChange={() => {}} />
                    </td>
                    <td className="py-3 px-2 w-[38%]">
                      <span className={`block font-medium leading-snug ${isDone ? 'line-through text-gray-400' : 'text-gray-800'}`}>
                        {t.task_name}
                      </span>
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap">
                      <div className={isDone ? 'opacity-40' : ''}>
                        <OwnerAvatar name={t.owner} />
                      </div>
                    </td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${isDone ? 'opacity-40' : ''} ${priorityBadge(t.priority)}`}>
                        {t.priority || '—'}
                      </span>
                    </td>
                    <td className="py-3 px-3 whitespace-nowrap" onClick={e => e.stopPropagation()}>
                      <div className="relative group/dl inline-flex items-center gap-1">
                        <span className={`text-xs ${isDone ? 'text-gray-400' : isOverdue(t) ? 'text-red-600 font-semibold' : 'text-gray-500'}`}>
                          {fmtDate(t.deadline) || <span className="text-gray-300 italic">No date</span>}
                        </span>
                        {/* Calendar edit icon — always visible on hover */}
                        <label
                          title="Edit deadline"
                          className="cursor-pointer text-gray-300 hover:text-indigo-500 transition-colors"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                            <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
                            <line x1="3" y1="10" x2="21" y2="10"/>
                          </svg>
                          <input
                            type="date"
                            className="absolute inset-0 opacity-0 cursor-pointer w-full"
                            value={toISODate(t.deadline)}
                            onChange={async (e) => {
                              const newDate = e.target.value // YYYY-MM-DD or ''
                              setTasks(prev => prev.map(x => x.id === t.id ? { ...x, deadline: newDate || 'Not specified' } : x))
                              try {
                                await fetch(`/api/tasks/${t.id}`, {
                                  method: 'PATCH',
                                  headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ deadline: newDate || '' }),
                                })
                              } catch { load() }
                            }}
                          />
                        </label>
                      </div>
                    </td>
                    <td className="py-3 px-3" onClick={e => e.stopPropagation()}>
                      <div className="relative inline-flex items-center group">
                        <select
                          value={t.status || 'Pending'}
                          onChange={async (e) => {
                            const newStatus = e.target.value
                            setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: newStatus } : x))
                            setFlashId(t.id)
                            setTimeout(() => setFlashId(null), 800)
                            try {
                              await fetch(`/api/tasks/${t.id}`, {
                                method: 'PATCH',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ status: newStatus }),
                              })
                            } catch { load() }
                          }}
                          className={`pl-2.5 pr-6 py-1 rounded-full text-xs font-semibold cursor-pointer appearance-none border transition-all
                            hover:shadow-md hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-indigo-300
                            ${statusBadge(t.status)}`}
                        >
                          <option value="Pending">Pending</option>
                          <option value="In Progress">In Progress</option>
                          <option value="Done">Done</option>
                          <option value="Cancelled">Cancelled</option>
                        </select>
                        {/* Chevron — sits inside the badge, non-interactive */}
                        <svg className="pointer-events-none absolute right-1.5 w-3 h-3 opacity-60" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7"/>
                        </svg>
                      </div>
                    </td>
                    <td className="py-3 px-3 pr-5 w-[20%]">
                      <span className="block text-xs text-gray-400 leading-snug">
                        {meetingTitle(t.meeting_summary)}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </>
        )}
      </div>
    </div>
    </>
  )
}

// ── Meetings Panel ─────────────────────────────────────────

function MeetingsPanel({ refreshTrigger }) {
  const [meetings,      setMeetings]      = useState([])
  const [taskMap,       setTaskMap]       = useState({})   // meeting_id → {total, done}
  const [tasksByMeeting,setTasksByMeeting]= useState({})   // meeting_id → task[]
  const [loading,       setLoading]       = useState(true)
  const [expanded,      setExpanded]      = useState(null)
  const [expandedTasks, setExpandedTasks] = useState(new Set()) // meeting_ids showing all tasks
  const [search,        setSearch]        = useState('')
  const [copied,        setCopied]        = useState(null) // meeting_id of copied card

  useEffect(() => {
    Promise.all([
      fetch('/api/meetings').then(r => r.json()),
      fetch('/api/tasks').then(r => r.json()),
    ]).then(([md, td]) => {
      setMeetings(md.meetings || [])
      // Build map: meeting_id → { total, done } and meeting_id → task[]
      const map = {}
      const byMeeting = {}
      for (const t of td.tasks || []) {
        if (!t.meeting_id) continue
        if (!map[t.meeting_id]) map[t.meeting_id] = { total: 0, done: 0 }
        map[t.meeting_id].total++
        if (t.status === 'Done') map[t.meeting_id].done++
        if (!byMeeting[t.meeting_id]) byMeeting[t.meeting_id] = []
        byMeeting[t.meeting_id].push(t)
      }
      setTaskMap(map)
      setTasksByMeeting(byMeeting)
    }).catch(console.error).finally(() => setLoading(false))
  }, [refreshTrigger])

  const fmt = (iso) => iso
    ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '—'

  const filtered = search.trim()
    ? meetings.filter(m =>
        (m.title   || '').toLowerCase().includes(search.toLowerCase()) ||
        (m.summary || '').toLowerCase().includes(search.toLowerCase())
      )
    : meetings

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-100 shrink-0 bg-white space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-gray-700">
            {filtered.length}{search ? ` of ${meetings.length}` : ''} meeting{meetings.length !== 1 ? 's' : ''}
          </span>
        </div>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search meetings by title or content…"
          className="w-full text-xs border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-100 bg-gray-50 placeholder-gray-400"
        />
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="text-center py-12 text-gray-400 text-sm">Loading meetings…</div>
        ) : meetings.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-60 gap-3 px-8 text-center">
            <span className="text-4xl opacity-40">📋</span>
            <p className="text-gray-500 font-medium text-sm">No meetings yet</p>
            <p className="text-gray-400 text-xs">Paste a meeting transcript in the chat. Catalyst will summarise it, extract tasks, and save it here automatically.</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-60 gap-3 text-center">
            <span className="text-4xl opacity-40">🔍</span>
            <p className="text-gray-500 font-medium text-sm">No meetings match "{search}"</p>
            <button onClick={() => setSearch('')} className="text-xs text-indigo-500 hover:underline">Clear search</button>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map(m => (
              <div key={m.meeting_id} className="border border-gray-200 rounded-xl overflow-hidden bg-white shadow-sm">
                <button
                  onClick={() => setExpanded(expanded === m.meeting_id ? null : m.meeting_id)}
                  className="w-full flex items-center justify-between px-4 py-3.5 hover:bg-gray-50 text-left transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-gray-800 truncate">{m.title}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <p className="text-xs text-gray-400">{fmt(m.created_at)}</p>
                      {taskMap[m.meeting_id] && (() => {
                        const { total, done } = taskMap[m.meeting_id]
                        const pct = total ? Math.round((done / total) * 100) : 0
                        return (
                          <div className="flex items-center gap-1.5">
                            <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full transition-all ${pct === 100 ? 'bg-emerald-500' : 'bg-indigo-500'}`} style={{ width: `${pct}%` }} />
                            </div>
                            <span className="text-[10px] text-gray-500 font-medium">{done}/{total}</span>
                            {pct === 100 && <span className="text-[10px] text-emerald-600 font-bold">✓ All done</span>}
                          </div>
                        )
                      })()}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-2 shrink-0">
                    {/* Copy summary button */}
                    <span
                      role="button"
                      title="Copy summary"
                      onClick={e => {
                        e.stopPropagation()
                        navigator.clipboard.writeText(m.summary || '').then(() => {
                          setCopied(m.meeting_id)
                          setTimeout(() => setCopied(null), 2000)
                        })
                      }}
                      className="p-1 rounded text-gray-300 hover:text-indigo-500 hover:bg-indigo-50 transition-colors"
                    >
                      {copied === m.meeting_id
                        ? <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/></svg>
                        : <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                      }
                    </span>
                    <svg
                      className={`w-4 h-4 text-gray-400 transition-transform ${expanded === m.meeting_id ? 'rotate-180' : ''}`}
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>
                {expanded === m.meeting_id && (
                  <div className="border-t border-gray-100 bg-gray-50">
                    <p className="px-4 pt-3 pb-2 text-sm text-gray-600 leading-relaxed">
                      {m.summary || 'No summary available.'}
                    </p>
                    {taskMap[m.meeting_id]?.total > 0 && (() => {
                      const mTasks = tasksByMeeting[m.meeting_id] || []
                      if (!mTasks.length) return null
                      const showAll = expandedTasks.has(m.meeting_id)
                      const visible = showAll ? mTasks : mTasks.slice(0, 5)
                      const remaining = mTasks.length - 5
                      return (
                        <div className="px-4 pb-3 border-t border-gray-100 mt-1">
                          <div className="flex items-center justify-between pt-2 mb-1.5">
                            <p className="text-[10px] font-semibold uppercase text-gray-400 tracking-wider">
                              Tasks ({mTasks.length})
                            </p>
                            {mTasks.length > 5 && (
                              <button
                                onClick={() => setExpandedTasks(prev => {
                                  const next = new Set(prev)
                                  next.has(m.meeting_id) ? next.delete(m.meeting_id) : next.add(m.meeting_id)
                                  return next
                                })}
                                className="text-[10px] text-indigo-500 hover:text-indigo-700 font-semibold hover:underline transition-colors"
                              >
                                {showAll ? '▲ Show less' : `+${remaining} more`}
                              </button>
                            )}
                          </div>
                          <div className="space-y-1">
                            {visible.map((t, ti) => (
                              <div key={ti} className="flex items-center gap-2 text-xs">
                                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                                  t.status === 'Done' ? 'bg-emerald-400' :
                                  t.status === 'Cancelled' ? 'bg-gray-300' : 'bg-indigo-400'
                                }`} />
                                <span className={`flex-1 truncate ${t.status === 'Done' ? 'line-through text-gray-400' : 'text-gray-600'}`}>
                                  {t.task_name}
                                </span>
                                <span className="text-gray-400 shrink-0 ml-2">{t.owner}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )
                    })()}
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

// ── SVG Trend Line Chart ───────────────────────────────────
function TrendLineChart({ weeks }) {
  if (!weeks?.length) return null
  const W = 400, H = 130
  const pad = { t: 14, r: 14, b: 26, l: 28 }
  const cW = W - pad.l - pad.r, cH = H - pad.t - pad.b
  const maxVal = Math.max(...weeks.flatMap(w => [w.tasks_created ?? 0, w.tasks_completed ?? 0]), 1)
  const xp = i => pad.l + (weeks.length > 1 ? (i / (weeks.length - 1)) * cW : cW / 2)
  const yp = v => pad.t + cH - (v / maxVal) * cH
  const pts = key => weeks.map((w, i) => `${xp(i)},${yp(w[key] ?? 0)}`).join(' ')
  const area = key => `${xp(0)},${pad.t + cH} ${pts(key)} ${xp(weeks.length - 1)},${pad.t + cH}`
  const gridVals = [0, Math.round(maxVal * 0.5), maxVal]

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 130 }}>
      <defs>
        <linearGradient id="lg-c" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#6366f1" stopOpacity="0.2"/><stop offset="100%" stopColor="#6366f1" stopOpacity="0"/>
        </linearGradient>
        <linearGradient id="lg-d" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#10b981" stopOpacity="0.2"/><stop offset="100%" stopColor="#10b981" stopOpacity="0"/>
        </linearGradient>
      </defs>
      {/* Grid */}
      {gridVals.map((v, i) => (
        <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={yp(v)} y2={yp(v)} stroke={i === 0 ? '#e5e7eb' : '#f3f4f6'} strokeWidth="1"/>
          <text x={pad.l - 4} y={yp(v) + 3} textAnchor="end" fontSize="7.5" fill="#cbd5e1">{v}</text>
        </g>
      ))}
      {/* Area fills */}
      <polygon points={area('tasks_created')} fill="url(#lg-c)"/>
      <polygon points={area('tasks_completed')} fill="url(#lg-d)"/>
      {/* Lines */}
      <polyline points={pts('tasks_created')} fill="none" stroke="#6366f1" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
      <polyline points={pts('tasks_completed')} fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
      {/* Dots */}
      {weeks.map((w, i) => (
        <g key={i}>
          <circle cx={xp(i)} cy={yp(w.tasks_created ?? 0)} r="4" fill="white" stroke="#6366f1" strokeWidth="2"/>
          <circle cx={xp(i)} cy={yp(w.tasks_completed ?? 0)} r="4" fill="white" stroke="#10b981" strokeWidth="2"/>
        </g>
      ))}
      {/* X labels */}
      {weeks.map((w, i) => {
        const lbl = String(w.week_label ?? w.week ?? `W${i+1}`)
        const short = lbl.includes('-') ? lbl.slice(5) : lbl.slice(0, 5)
        return <text key={i} x={xp(i)} y={H - 5} textAnchor="middle" fontSize="8" fill="#94a3b8">{short}</text>
      })}
    </svg>
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

// ── Skeleton loader ────────────────────────────────────────
function Skeleton({ className = '' }) {
  return <div className={`animate-pulse bg-gray-200 rounded-lg ${className}`} />
}

function AnalyticsPanel({ onOwnerClick, onTabChange, onTasksNav, onTaskUpdated }) {
  const [data,        setData]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [doneIds,     setDoneIds]     = useState(new Set())
  const [spinning,    setSpinning]    = useState(false)
  const [avgQuality,  setAvgQuality]  = useState(null)  // avg overall_score across all runs

  const reload = (manual = false) => {
    if (manual) setSpinning(true)
    else setLoading(true)
    Promise.all([
      fetch('/api/analytics').then(r => r.json()),
      fetch('/api/quality').then(r => r.json()).catch(() => null),
    ]).then(([analytics, quality]) => {
      setData(analytics)
      const scores = quality?.quality_scores ?? []
      if (scores.length > 0) {
        const avg = scores.reduce((s, q) => s + (q.overall_score ?? 0), 0) / scores.length
        setAvgQuality(avg.toFixed(1))
      }
    }).catch(console.error)
      .finally(() => { setLoading(false); setSpinning(false) })
  }
  useEffect(() => reload(), [])

  // ── Skeleton state ──────────────────────────────────────
  if (loading) return (
    <div className="flex flex-col h-full overflow-y-auto px-5 py-5 space-y-5 bg-gray-50">
      <div className="flex items-center justify-between -mb-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-6 w-6 rounded-full" />
      </div>
      {/* Stat card skeletons */}
      <div className="grid grid-cols-4 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm space-y-2">
            <Skeleton className="h-7 w-12" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))}
      </div>
      {/* Ownership bar skeletons */}
      <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm space-y-3">
        <Skeleton className="h-3 w-28 mb-1" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="space-y-1.5">
            <div className="flex justify-between">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-24" />
            </div>
            <Skeleton className={`h-2.5 rounded-full`} style={{ width: `${70 - i * 12}%` }} />
          </div>
        ))}
      </div>
      {/* Weekly chart skeleton */}
      <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
        <Skeleton className="h-3 w-28 mb-4" />
        <div className="flex items-end gap-2 h-24">
          {[60,80,45,90,70,55].map((h, i) => (
            <div key={i} className="flex-1 flex gap-0.5 items-end h-full">
              <Skeleton className="flex-1 rounded-t" style={{ height: `${h}%` }} />
              <Skeleton className="flex-1 rounded-t" style={{ height: `${h * 0.6}%` }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  // ── Empty state ─────────────────────────────────────────
  const isEmpty = !data ||
    ((data.velocity?.total_tasks ?? data.velocity?.velocity?.total_tasks ?? 0) === 0 &&
     (data.ownership?.owners?.length ?? 0) === 0)

  if (isEmpty) return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-gray-400 px-8 text-center">
      <span className="text-5xl opacity-30">📊</span>
      <p className="text-base font-semibold text-gray-500">No data yet</p>
      <p className="text-sm leading-relaxed max-w-xs">
        Process your first meeting transcript in the chat to see task ownership, trends, and quality scores here.
      </p>
      <button
        onClick={() => onTabChange?.('tasks')}
        className="mt-1 px-4 py-2 bg-indigo-600 text-white text-xs font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
      >
        Go to Tasks
      </button>
    </div>
  )

  const velocity    = data.velocity?.velocity ?? data.velocity ?? {}
  const owners      = data.ownership?.owners  ?? []
  const overdueList = (data.overdue?.overdue_tasks ?? data.overdue?.tasks ?? []).filter(t => !doneIds.has(t.id))
  const weeks       = (data.trends?.weeks     ?? data.trends?.trend ?? []).slice(-6)
  const openTasks   = Math.max(0, (velocity.total_tasks ?? 0) - (velocity.completed_tasks ?? 0))
  const completionPct = velocity.total_tasks
    ? Math.round((velocity.completed_tasks ?? 0) / velocity.total_tasks * 100) : 0
  const COLORS = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444']

  // Time saved: each task ~2 min to manually document + meeting summary ~8 min baseline
  const totalTasks  = velocity.total_tasks ?? 0
  const timeSavedMin = Math.round(totalTasks * 2 + (velocity.total_meetings ?? 0) * 8)
  const timeSavedStr = timeSavedMin >= 60
    ? `${Math.floor(timeSavedMin / 60)}h ${timeSavedMin % 60}m`
    : `${timeSavedMin}m`

  // Cost saved: time saved × $150/hr avg knowledge worker rate
  const costSavedUSD = Math.round((timeSavedMin / 60) * 150)
  const costSavedStr = costSavedUSD >= 1000
    ? `$${(costSavedUSD / 1000).toFixed(1)}k`
    : `$${costSavedUSD}`

  // Duplicates blocked — sum high_priority_open proxy or read from ownership
  const duplicatesBlocked = owners.reduce((acc, o) => acc + (o.duplicates_blocked ?? 0), 0)

  const markDone = async (task) => {
    setDoneIds(s => new Set([...s, task.id]))
    try {
      await fetch(`/api/tasks/${task.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'Done' }),
      })
      onTaskUpdated?.()
    } catch {
      setDoneIds(s => { const n = new Set(s); n.delete(task.id); return n })
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto px-5 py-5 space-y-5 bg-gray-50">

      {/* Header row with refresh */}
      <div className="flex items-center justify-between -mb-2">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Overview</span>
        <button
          onClick={() => reload(true)}
          title="Refresh analytics"
          className="p-1.5 rounded-lg text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
        >
          <svg className={`w-4 h-4 ${spinning ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {/* Stat Cards — clickable */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { icon:'📅', label:'Meetings',   value: velocity.total_meetings ?? 0,        color:'text-indigo-700', action: () => onTabChange('meetings') },
          { icon:'📌', label:'Open Tasks', value: openTasks,                            color:'text-amber-700',  action: () => onTasksNav('Pending') },
          { icon:'⚠️', label:'Overdue',    value: data.overdue?.overdue_tasks?.length ?? 0, color:'text-red-600', action: () => onTasksNav('Overdue') },
          { icon:'✅', label:'Completion', value: `${completionPct}%`,                 color:'text-emerald-700',action: () => onTasksNav('Done') },
          { icon:'🏅', label:'Avg Quality',value: avgQuality ? `${avgQuality}/5` : '—', color: avgQuality >= 4 ? 'text-emerald-700' : avgQuality >= 3 ? 'text-amber-600' : 'text-gray-400', action: null },
        ].map(c => (
          <div
            key={c.label}
            onClick={c.action || undefined}
            className={`bg-white border border-gray-200 rounded-xl p-4 shadow-sm flex items-start justify-between ${c.action ? 'cursor-pointer hover:border-indigo-300 hover:shadow-md transition-all' : ''}`}
          >
            <div>
              <p className={`text-2xl font-bold ${c.color}`}>{c.value}</p>
              <p className="text-xs font-medium text-gray-500 mt-0.5">{c.label}</p>
            </div>
            <span className="text-xl opacity-50">{c.icon}</span>
          </div>
        ))}
      </div>

      {/* Impact Row — time saved + cost saved + duplicates blocked */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-gradient-to-br from-indigo-50 to-indigo-100/60 border border-indigo-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">⏱️</span>
            <span className="text-xs font-bold text-indigo-600 uppercase tracking-wider">Est. Time Saved</span>
          </div>
          <p className="text-2xl font-bold text-indigo-700">{timeSavedStr}</p>
          <p className="text-xs text-indigo-500 mt-0.5">{totalTasks} tasks × 2 min + {velocity.total_meetings ?? 0} summaries × 8 min</p>
        </div>
        <div className="bg-gradient-to-br from-amber-50 to-amber-100/60 border border-amber-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">💰</span>
            <span className="text-xs font-bold text-amber-600 uppercase tracking-wider">Est. Cost Saved</span>
          </div>
          <p className="text-2xl font-bold text-amber-700">{costSavedStr}</p>
          <p className="text-xs text-amber-500 mt-0.5">{timeSavedStr} saved × $150/hr avg knowledge worker rate</p>
        </div>
        <div className="bg-gradient-to-br from-emerald-50 to-emerald-100/60 border border-emerald-200 rounded-xl p-4 shadow-sm">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">🛡️</span>
            <span className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Duplicates Blocked</span>
          </div>
          <p className="text-2xl font-bold text-emerald-700">{velocity.duplicates_blocked ?? duplicatesBlocked}</p>
          <p className="text-xs text-emerald-500 mt-0.5">Semantic deduplication via pgvector · Vertex AI embeddings</p>
        </div>
      </div>

      {/* Smart Insights */}
      {(() => {
        const insights = []
        if (overdueList.length > 0) {
          const w = overdueList[0]
          insights.push({ icon: '⚠️', text: `"${w.task_name.slice(0, 40)}${w.task_name.length > 40 ? '…' : ''}" is ${w.days_overdue}d overdue`, color: 'text-red-600 bg-red-50 border-red-100' })
        }
        const overloaded = owners.find(o => o.high_priority_open > 2)
        if (overloaded) insights.push({ icon: '🔥', text: `${overloaded.owner} has ${overloaded.high_priority_open} high-priority tasks open`, color: 'text-orange-600 bg-orange-50 border-orange-100' })
        const lastWeek = weeks[weeks.length - 1]
        if (lastWeek) {
          const created = lastWeek.tasks_created ?? 0, done = lastWeek.tasks_completed ?? 0
          if (done > created && done > 0) insights.push({ icon: '🚀', text: 'Closing faster than creating this week — great momentum!', color: 'text-emerald-600 bg-emerald-50 border-emerald-100' })
          else if (created - done > 2) insights.push({ icon: '📈', text: `${created - done} more tasks added than closed this week — backlog growing`, color: 'text-amber-600 bg-amber-50 border-amber-100' })
        }
        if (completionPct >= 75) insights.push({ icon: '🏆', text: `${completionPct}% overall completion rate — excellent team performance`, color: 'text-indigo-600 bg-indigo-50 border-indigo-100' })
        if (!insights.length) return null
        return (
          <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">💡 Insights</h3>
            <div className="space-y-2">
              {insights.map((ins, i) => (
                <div key={i} className={`flex items-start gap-2 text-xs font-medium px-3 py-2 rounded-lg border ${ins.color}`}>
                  <span className="shrink-0">{ins.icon}</span>
                  <span>{ins.text}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      {/* Task Ownership — click bar to filter task board */}
      {owners.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Task Ownership</h3>
            <span className="text-xs text-indigo-500 font-medium">Click a bar to filter tasks →</span>
          </div>
          <div className="space-y-3">
            {owners.slice(0, 7).map((o, i) => {
              const maxTasks = owners[0]?.total_tasks || 1
              const pct = Math.round((o.total_tasks / maxTasks) * 100)
              return (
                <button
                  key={o.owner}
                  className="w-full text-left group"
                  onClick={() => { onOwnerClick(o.owner); onTabChange('tasks') }}
                >
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="font-semibold text-gray-700 group-hover:text-indigo-600 transition-colors">{o.owner}</span>
                    <span className="text-gray-400">{o.total_tasks} tasks · <span className="text-emerald-600 font-medium">{o.completion_pct ?? 0}% done</span></span>
                  </div>
                  <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden group-hover:bg-indigo-50 transition-colors">
                    <div className="h-full rounded-full transition-all duration-500 group-hover:opacity-80"
                      style={{ width: `${pct}%`, backgroundColor: COLORS[i % COLORS.length] }} />
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Overdue Tasks — inline Mark Done (no LLM) */}
      {overdueList.length > 0 && (
        <div className="bg-white rounded-xl border border-red-100 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-red-500 uppercase tracking-wider">⚠️ Overdue Tasks</h3>
            <span className="text-xs text-gray-400">Mark done without using the chat</span>
          </div>
          <div className="space-y-2">
            {overdueList.slice(0, 8).map(t => {
              const urgent = t.days_overdue > 7
              const critical = t.days_overdue > 14
              return (
              <div key={t.id} className={`flex justify-between items-center rounded-lg px-3 py-2.5 gap-2 ${
                critical ? 'bg-red-100' : urgent ? 'bg-red-50' : 'bg-orange-50'
              }`}>
                <span className="text-sm text-gray-700 font-medium leading-snug flex-1" style={{ overflowWrap:'anywhere' }}>
                  {t.task_name}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-gray-500">{t.owner || '?'}</span>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full whitespace-nowrap ${
                    critical ? 'bg-red-600 text-white' :
                    urgent   ? 'bg-red-500 text-white' :
                               'bg-orange-400 text-white'
                  }`}>
                    {t.days_overdue}d late
                  </span>
                  <button
                    onClick={() => markDone(t)}
                    className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-2.5 py-1 rounded-lg transition-colors whitespace-nowrap"
                  >
                    ✓ Done
                  </button>
                </div>
              </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Weekly Trend — SVG Line Chart */}
      {weeks.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider">Weekly Activity</h3>
            <div className="flex gap-3">
              <span className="flex items-center gap-1.5 text-xs text-gray-500">
                <span className="w-3 h-1.5 rounded-full bg-indigo-500 inline-block"/>Created
              </span>
              <span className="flex items-center gap-1.5 text-xs text-gray-500">
                <span className="w-3 h-1.5 rounded-full bg-emerald-500 inline-block"/>Completed
              </span>
            </div>
          </div>
          <TrendLineChart weeks={weeks} />
        </div>
      )}

    </div>
  )
}

// ── Docs Panel ─────────────────────────────────────────────

function DocsPanel({ refreshTrigger }) {
  const [docs,    setDocs]    = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch('/api/docs').then(r => r.json()).then(d => setDocs(d.docs ?? [])).catch(console.error).finally(() => setLoading(false))
  }, [refreshTrigger])

  const docTitle = (summary) => {
    if (!summary) return 'Meeting Notes'
    // Extract meeting name: "The Q3 Planning meeting on..." → "Q3 Planning"
    const nameMatch = summary.match(/^(?:The |A |This )?(.+?)\s+(?:meeting|session|call|standup|sync|review)\b/i)
    if (nameMatch) return nameMatch[1].trim().slice(0, 60)
    // Fallback: first sentence capped at 45 chars
    const first = summary.split(/[.\n]/)[0].trim()
    return first.replace(/^(The |This |A )/i, '').slice(0, 45) || 'Meeting Notes'
  }

  const fmtDateTime = (val) => {
    if (!val) return '—'
    const d = new Date(val)
    return isNaN(d) ? val : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  if (loading) return (
    <div className="flex items-center justify-center h-40 text-gray-400 text-sm gap-2">
      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
      Loading documents…
    </div>
  )

  if (docs.length === 0) return (
    <div className="flex flex-col items-center justify-center h-60 text-gray-400 gap-3">
      <span className="text-4xl opacity-40">📄</span>
      <p className="text-sm font-medium">No documents yet</p>
      <p className="text-xs text-center max-w-xs">After processing a transcript, Catalyst automatically publishes a formatted Google Doc. It will appear here.</p>
    </div>
  )

  return (
    <div className="flex flex-col h-full overflow-y-auto px-5 py-5 bg-gray-50">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-bold text-gray-600 uppercase tracking-wider">Published Meeting Docs</h2>
        <span className="text-xs text-gray-400">{docs.length} document{docs.length !== 1 ? 's' : ''}</span>
      </div>
      <div className="space-y-3">
        {docs.map(doc => (
          <div key={doc.id} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:border-indigo-200 hover:shadow-md transition-all group">
            <div className="flex items-start gap-3">
              {/* Doc icon */}
              <div className="w-10 h-10 rounded-lg bg-indigo-50 flex items-center justify-center text-xl shrink-0 group-hover:bg-indigo-100 transition-colors">
                📄
              </div>
              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-gray-800 leading-snug" style={{ overflowWrap: 'anywhere' }}>
                  {docTitle(doc.summary)}
                </p>
                <p className="text-xs text-gray-400 mt-1">{fmtDateTime(doc.created_at)}</p>
                {doc.summary && (
                  <p className="text-xs text-gray-500 mt-2 leading-relaxed line-clamp-2">
                    {doc.summary.slice(0, 160)}{doc.summary.length > 160 ? '…' : ''}
                  </p>
                )}
              </div>
              {/* Open button */}
              <a
                href={doc.doc_url}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 flex items-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg transition-colors shadow-sm whitespace-nowrap"
              >
                Open ↗
              </a>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Root App ───────────────────────────────────────────────

const TABS = [
  { id: 'tasks',     label: 'Tasks',    icon: '✅' },
  { id: 'meetings',  label: 'Meetings', icon: '📋' },
  { id: 'analytics', label: 'Analytics',icon: '📊' },
  { id: 'docs',      label: 'Docs',     icon: '📄' },
]

export default function App() {
  const [tab,            setTab]            = useState('tasks')
  const [refreshTrigger, setRefreshTrigger] = useState(0)
  const [ownerFilter,    setOwnerFilter]    = useState(null)
  const [statusFilter,   setStatusFilter]   = useState('all')
  const [tabCounts,      setTabCounts]      = useState({ tasks: 0, overdue: 0, meetings: 0 })
  const [bannerDismissed, setBannerDismissed] = useState(false)

  // Re-show banner whenever overdue count increases
  const prevOverdue = useRef(0)
  useEffect(() => {
    if (tabCounts.overdue > prevOverdue.current) setBannerDismissed(false)
    prevOverdue.current = tabCounts.overdue
  }, [tabCounts.overdue])

  // Fetch counts for tab badges — pure DB reads, no LLM
  useEffect(() => {
    const load = async () => {
      try {
        const [tr, mr] = await Promise.all([
          fetch('/api/tasks').then(r => r.json()),
          fetch('/api/meetings').then(r => r.json()),
        ])
        const tasks = tr.tasks || []
        const today = new Date(); today.setHours(0,0,0,0)
        const overdue = tasks.filter(t => {
          if (t.status === 'Done' || t.status === 'Cancelled') return false
          if (!t.deadline || t.deadline === 'TBD' || t.deadline === 'Not specified') return false
          const d = new Date(t.deadline)
          return !isNaN(d) && d < today
        }).length
        setTabCounts({ tasks: tasks.filter(t => t.status === 'Pending' || t.status === 'In Progress').length, overdue, meetings: (mr.meetings || []).length })
      } catch {}
    }
    load()
  }, [refreshTrigger])

  const triggerRefresh = () => setRefreshTrigger(n => n + 1)

  const handleOwnerClick = (owner) => {
    setOwnerFilter(owner)
    setTab('tasks')
  }

  const handleTasksNav = (status = 'all') => {
    setStatusFilter(status)
    setTab('tasks')
  }

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
          {TABS.map(t => {
            const badge = t.id === 'tasks' ? tabCounts.tasks : t.id === 'meetings' ? tabCounts.meetings : 0
            const hasOverdue = t.id === 'tasks' && tabCounts.overdue > 0
            return (
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
              {badge > 0 && (
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center leading-none ${
                  hasOverdue ? 'bg-red-100 text-red-600' : 'bg-indigo-100 text-indigo-600'
                }`}>
                  {hasOverdue ? `${tabCounts.overdue}⏰` : badge}
                </span>
              )}
            </button>
          )})}

        </div>

        {/* Overdue banner — shows whenever there are overdue tasks */}
        {!bannerDismissed && tabCounts.overdue > 0 && (
          <div className="mx-4 mt-2.5 mb-0.5 flex items-center gap-3 bg-red-50 border border-red-200 rounded-xl px-4 py-2.5 shrink-0 shadow-sm">
            <span className="text-base shrink-0">⚠️</span>
            <p className="text-sm text-red-700 flex-1 font-medium">
              <span className="font-bold">{tabCounts.overdue} task{tabCounts.overdue > 1 ? 's' : ''} overdue</span>
              {' — '}
              <button
                onClick={() => { handleTasksNav('Overdue') }}
                className="underline underline-offset-2 hover:text-red-900 transition-colors"
              >
                view &amp; mark done
              </button>
              {' or ask Catalyst "What\'s overdue?"'}
            </p>
            <button
              onClick={() => setBannerDismissed(true)}
              className="shrink-0 text-red-400 hover:text-red-600 transition-colors text-lg leading-none"
              title="Dismiss"
            >×</button>
          </div>
        )}

        {/* Tab content */}
        <div className="flex-1 overflow-hidden">
          {tab === 'tasks'     && <TaskBoard     refreshTrigger={refreshTrigger} ownerFilter={ownerFilter} onClearOwner={() => setOwnerFilter(null)} statusFilter={statusFilter} onClearStatus={() => setStatusFilter('all')} onCountsChange={(counts) => setTabCounts(prev => ({ ...prev, ...counts }))} />}
          {tab === 'meetings'  && <MeetingsPanel refreshTrigger={refreshTrigger} />}
          {tab === 'analytics' && <AnalyticsPanel onOwnerClick={handleOwnerClick} onTabChange={setTab} onTasksNav={handleTasksNav} onTaskUpdated={() => setRefreshTrigger(r => r + 1)} />}
          {tab === 'docs'      && <DocsPanel      refreshTrigger={refreshTrigger} />}
        </div>
      </div>
    </div>
  )
}

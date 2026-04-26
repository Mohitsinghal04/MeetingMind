import { useState, useEffect, useRef, useCallback } from 'react'
import { marked } from 'marked'

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

// ── Pipeline Visualizer ────────────────────────────────────

const PIPELINE_STAGES = [
  { label: 'Summarise', icon: '📝' },
  { label: 'Save',      icon: '💾' },
  { label: 'Notes',     icon: '📓' },
  { label: 'Briefing',  icon: '✨' },
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
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-500 shrink-0
                ${done   ? 'bg-emerald-500 text-white'
                : active ? 'bg-indigo-500 text-white animate-pulse'
                         : 'bg-gray-100 text-gray-400'}`}>
                {done ? '✓' : s.icon}
              </div>
              {i < PIPELINE_STAGES.length - 1 && (
                <div className={`flex-1 h-0.5 mx-1 rounded transition-all duration-500
                  ${i < currentStage || complete ? 'bg-emerald-400' : 'bg-gray-100'}`} />
              )}
            </div>
          )
        })}
      </div>
      {/* Labels row — each label centred under its circle */}
      <div className="flex mt-1.5">
        {PIPELINE_STAGES.map((s, i) => {
          const done   = complete || i < currentStage
          const active = !complete && i === currentStage
          return (
            <div key={s.label} className="flex-1 flex justify-start">
              <span className={`text-xs font-medium transition-colors duration-300 leading-tight
                ${done   ? 'text-emerald-600'
                : active ? 'text-indigo-600'
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

const WELCOME = '👋 **Welcome to MeetingMind!**\n\nI\'m powered by **8 specialized agents** working together to process your meetings.\n\n**Try:**\n- Paste any meeting transcript (500+ chars)\n- "What tasks are pending?"\n- "Who has the most tasks?"\n- "What\'s overdue?"'

const MESSAGES_KEY = 'mm_messages'

// ── Speech Recognition hook ────────────────────────────────
function useSpeechRecognition({ onFinalText, onInterim }) {
  const recRef   = useRef(null)
  const timerRef = useRef(null)
  const [isRecording, setIsRecording] = useState(false)
  const [duration,    setDuration]    = useState(0)
  const [supported,   setSupported]   = useState(false)

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    setSupported(!!SR)
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
        try { recRef.current.start() } catch {}
      }
    }

    recRef.current = rec
    rec.start()
    setIsRecording(true)
    setDuration(0)
    timerRef.current = setInterval(() => setDuration(d => d + 1), 1000)
  }, [onFinalText, onInterim])

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

function ChatPanel({ onTranscriptProcessed, onTaskUpdated }) {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem(MESSAGES_KEY)
      return saved ? JSON.parse(saved) : [{ role: 'assistant', text: WELCOME }]
    } catch { return [{ role: 'assistant', text: WELCOME }] }
  })
  const [input,         setInput]         = useState('')
  const [loading,       setLoading]       = useState(false)
  const [pipelineStage, setPipelineStage] = useState(-1)  // -1 = not active
  const [isTranscript,  setIsTranscript]  = useState(false)
  const [interimText,   setInterimText]   = useState('')
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
    useSpeechRecognition({ onFinalText, onInterim: setInterimText })

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

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(m => [...m, { role: 'user', text: msg }])
    setLoading(true)
    const wasTaskCommand  = isTaskUpdate(msg)
    const msgIsTranscript = msg.length > 400
    setIsTranscript(msgIsTranscript)
    setPipelineStage(msgIsTranscript ? 0 : -1)


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
            if (evt.type === 'response') reply = evt.response || '⚠️ No response.'
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

      setMessages(m => [...m, { role: 'assistant', text: reply }])

      if (isProcessed) {
        onTranscriptProcessed?.()
        // Fetch quality score and append as special message
        try {
          const q = await fetch('/api/quality').then(r => r.json())
          const latest = (q?.quality_scores ?? [])[0] ?? null
          if (latest?.overall_score) {
            setMessages(m => [...m, { role: 'quality', data: latest }])
          }
        } catch {}
      } else if (wasTaskCommand && isTaskUpdateConfirm(reply)) {
        onTaskUpdated?.()
      }
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', text: `⚠️ ${e.message}` }])
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
    <div className="flex flex-col h-full bg-white">
      {/* Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-indigo-600 to-indigo-500 text-white flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="text-lg font-bold tracking-tight">🧠 MeetingMind</span>
          <span className="text-xs bg-white/20 backdrop-blur px-2.5 py-0.5 rounded-full font-medium">10 Agents</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setInput(DEMO_TRANSCRIPT)}
            className="text-xs bg-white/20 hover:bg-white/30 backdrop-blur px-2.5 py-1 rounded-full font-medium transition-colors"
            title="Load a sample transcript to demo the full pipeline"
          >
            ▶ Try Demo
          </button>
          <span className="text-xs text-indigo-200 font-medium">AI Meeting Intelligence</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4 bg-gray-50">
        {messages.map((m, i) => {
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
                    dangerouslySetInnerHTML={{ __html: renderMd(m.text) }}
                  />
                ) : (
                  <span style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{m.text}</span>
                )}
              </div>
            </div>
          )
        })}

        {loading && (
          <div className="flex justify-start items-start gap-2">
            <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-sm shrink-0">🧠</div>
            <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm min-w-[260px]">
              <p className="text-xs text-gray-500 mb-3 flex items-center gap-1.5 font-medium">
                <span className="animate-spin inline-block">⚙️</span>
                {isTranscript ? 'Pipeline running…' : 'Agents working…'}
              </p>
              {isTranscript ? (
                <PipelineVisualizer currentStage={pipelineStage} complete={false} />
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
            placeholder={isRecording ? 'Recording… speak your meeting transcript' : 'Paste a transcript or ask a question…'}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={onKey}
            disabled={loading}
          />
          <div className="flex flex-col gap-1.5 shrink-0">
            {/* Mic button */}
            {supported && (
              <button
                onClick={toggleMic}
                disabled={loading}
                title={isRecording ? 'Stop recording' : 'Record live meeting'}
                className={`p-2.5 rounded-xl text-sm font-semibold transition-all shadow-sm disabled:opacity-40 disabled:cursor-not-allowed ${
                  isRecording
                    ? 'bg-red-500 hover:bg-red-600 text-white ring-2 ring-red-300 ring-offset-1'
                    : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
                }`}
              >
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
            )}
            {/* Send button */}
            <button
              onClick={send}
              disabled={loading || !input.trim()}
              className="px-4 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              Send
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-400 mt-1.5 pl-1">
          {isRecording
            ? '🔴 Recording live — click ■ to stop, then Send to process'
            : 'Enter to send · Shift+Enter for newline · 🎙 mic to record live'}
        </p>
      </div>
    </div>
  )
}

// ── Task Board ─────────────────────────────────────────────

const PRIORITY_ORDER = { High: 0, Medium: 1, Low: 2 }

function TaskBoard({ refreshTrigger, ownerFilter, onClearOwner, statusFilter, onClearStatus }) {
  const [tasks,   setTasks]   = useState([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState(statusFilter ?? 'all')
  const [search,  setSearch]  = useState('')
  const [sortBy,  setSortBy]  = useState('priority') // 'priority' | 'deadline'

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

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="px-5 py-3 border-b border-gray-100 bg-white shrink-0 space-y-2">
        {/* Row 1: status filters + refresh */}
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
          <button onClick={load} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors" title="Refresh">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
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
            <p className="text-gray-400 text-xs">Paste a meeting transcript in the chat — MeetingMind will extract and prioritise action items automatically.</p>
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center gap-2">
            <span className="text-2xl">🔍</span>
            <p className="text-gray-400 text-xs">No tasks match "{search}"</p>
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
              {visible.map((t, idx) => {
                const isDone = t.status === 'Done' || t.status === 'Cancelled'
                return (
                  <tr
                    key={t.id || idx}
                    className={`border-b border-gray-50 transition-colors ${
                      isDone ? 'bg-gray-50/50 hover:bg-gray-100/50' : 'hover:bg-indigo-50/30'
                    }`}
                  >
                    <td className="py-3 px-5 w-[40%]">
                      <span className={`block font-medium leading-snug ${isDone ? 'line-through text-gray-400' : 'text-gray-800'}`}>
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
                      <div className="relative inline-flex items-center group">
                        <select
                          value={t.status || 'Pending'}
                          onChange={async (e) => {
                            const newStatus = e.target.value
                            setTasks(prev => prev.map(x => x.id === t.id ? { ...x, status: newStatus } : x))
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
  const [search,   setSearch]   = useState('')

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
            <p className="text-gray-400 text-xs">Paste a meeting transcript in the chat. MeetingMind will summarise it, extract tasks, and save it here automatically.</p>
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
                    {m.summary || 'No summary available.'}
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

function AnalyticsPanel({ onOwnerClick, onTabChange, onTasksNav, onTaskUpdated }) {
  const [data,      setData]      = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [doneIds,   setDoneIds]   = useState(new Set())
  const [spinning,  setSpinning]  = useState(false)

  const reload = (manual = false) => {
    if (manual) setSpinning(true)
    else setLoading(true)
    fetch('/api/analytics')
      .then(r => r.json()).then(setData).catch(console.error)
      .finally(() => { setLoading(false); setSpinning(false) })
  }
  useEffect(() => reload(), [])

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

  const velocity    = data.velocity?.velocity ?? data.velocity ?? {}
  const owners      = data.ownership?.owners  ?? []
  const overdueList = (data.overdue?.overdue_tasks ?? data.overdue?.tasks ?? []).filter(t => !doneIds.has(t.id))
  const weeks       = (data.trends?.weeks     ?? data.trends?.trend ?? []).slice(-6)
  const openTasks   = Math.max(0, (velocity.total_tasks ?? 0) - (velocity.completed_tasks ?? 0))
  const completionPct = velocity.total_tasks
    ? Math.round((velocity.completed_tasks ?? 0) / velocity.total_tasks * 100) : 0
  const COLORS = ['#6366f1','#8b5cf6','#ec4899','#f59e0b','#10b981','#3b82f6','#ef4444']

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
      <div className="grid grid-cols-4 gap-3">
        {[
          { icon:'📅', label:'Meetings',   value: velocity.total_meetings ?? 0,        color:'text-indigo-700', action: () => onTabChange('meetings') },
          { icon:'📌', label:'Open Tasks', value: openTasks,                            color:'text-amber-700',  action: () => onTasksNav('Pending') },
          { icon:'⚠️', label:'Overdue',    value: data.overdue?.overdue_tasks?.length ?? 0, color:'text-red-600', action: () => onTasksNav('Overdue') },
          { icon:'✅', label:'Completion', value: `${completionPct}%`,            color:'text-emerald-700',action: () => onTasksNav('Done') },
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
            {overdueList.slice(0, 8).map(t => (
              <div key={t.id} className="flex justify-between items-center bg-red-50 rounded-lg px-3 py-2.5 gap-2">
                <span className="text-sm text-gray-700 font-medium leading-snug flex-1" style={{ overflowWrap:'anywhere' }}>
                  {t.task_name}
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-gray-500">{t.owner || '?'}</span>
                  <span className="text-xs bg-red-100 text-red-700 font-semibold px-2 py-0.5 rounded-full whitespace-nowrap">
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
            ))}
          </div>
        </div>
      )}

      {/* Weekly Trend */}
      {weeks.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <h3 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4">Weekly Activity</h3>
          <div className="flex items-end gap-2 h-24">
            {weeks.map((w, i) => {
              const maxVal = Math.max(...weeks.map(x => x.tasks_created ?? x.created ?? 0), 1)
              const created   = w.tasks_created ?? w.created   ?? 0
              const completed = w.tasks_completed ?? w.completed ?? 0
              return (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full flex gap-0.5 items-end h-16">
                    <div className="flex-1 bg-indigo-200 rounded-t transition-all" style={{ height: `${(created/maxVal)*100}%`, minHeight: created ? 4 : 0 }} title={`Created: ${created}`} />
                    <div className="flex-1 bg-emerald-400 rounded-t transition-all" style={{ height: `${(completed/maxVal)*100}%`, minHeight: completed ? 4 : 0 }} title={`Done: ${completed}`} />
                  </div>
                  <span className="text-xs text-gray-400 truncate w-full text-center">
                    {w.week_label ?? w.week ?? `W${i+1}`}
                  </span>
                </div>
              )
            })}
          </div>
          <div className="flex gap-4 mt-2">
            <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-3 h-3 rounded-sm bg-indigo-200 inline-block"/>Created</span>
            <span className="flex items-center gap-1.5 text-xs text-gray-500"><span className="w-3 h-3 rounded-sm bg-emerald-400 inline-block"/>Completed</span>
          </div>
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
      <p className="text-xs text-center max-w-xs">After processing a transcript, MeetingMind automatically publishes a formatted document. It will appear here.</p>
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
          {tab === 'tasks'     && <TaskBoard     refreshTrigger={refreshTrigger} ownerFilter={ownerFilter} onClearOwner={() => setOwnerFilter(null)} statusFilter={statusFilter} onClearStatus={() => setStatusFilter('all')} />}
          {tab === 'meetings'  && <MeetingsPanel />}
          {tab === 'analytics' && <AnalyticsPanel onOwnerClick={handleOwnerClick} onTabChange={setTab} onTasksNav={handleTasksNav} onTaskUpdated={() => setRefreshTrigger(r => r + 1)} />}
          {tab === 'docs'      && <DocsPanel      refreshTrigger={refreshTrigger} />}
        </div>
      </div>
    </div>
  )
}

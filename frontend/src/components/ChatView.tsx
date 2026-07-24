import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, listMessages } from '../lib/api'
import { InvalidDoneUsageError, streamMessage } from '../lib/sse'
import type { ConversationView, Message, ResponseUsage } from '../lib/types'
import './ChatView.css'

type DisplayMessage = Message | { id: string; role: 'assistant'; content: string; created_at: string }
type StreamSession = {
  userMessage: Message
  assistantMessage: Extract<DisplayMessage, { role: 'assistant' }>
  toolSelectionMessage: string | null
  error: string | null
  completed: boolean
}

type ResponsePerformance = {
  usage: ResponseUsage
  ttftMs: number | null
  generationTokensPerSecond: number | null
}

const titleFrom = (message: string) => Array.from(message).slice(0, 30).join('')
const formatInteger = (value: number) => value.toLocaleString('ko-KR')

function formatContextUsage(usage: ResponseUsage): string {
  if (usage.context_limit === null) return '—'
  const used = usage.input_tokens + usage.output_tokens
  const percent = Math.round((used / usage.context_limit) * 100)
  return `${formatInteger(used)} / ${formatInteger(usage.context_limit)} (${percent}%)`
}

const formatTtft = (value: number | null) =>
  value === null ? '—' : `${Math.round(value).toLocaleString('ko-KR')} ms`

const formatGenerationSpeed = (value: number | null) =>
  value === null ? '—' : `${value.toFixed(1)} tok/s`

function previewForCreatedConversation(session: StreamSession): DisplayMessage[] {
  return session.completed ? [session.userMessage] : [session.userMessage, session.assistantMessage]
}

function mergeStreamSession(messages: Message[], session: StreamSession): DisplayMessage[] {
  if (session.completed) return messages
  const lastMessage = messages[messages.length - 1]
  const hasCurrentUserMessage = lastMessage?.role === 'user' && lastMessage.content === session.userMessage.content
  return [...messages, ...(hasCurrentUserMessage ? [] : [session.userMessage]), session.assistantMessage]
}

export function ChatView({ conversation, onCreateConversation, onStreamingChange, onSessionExpired }: { conversation: ConversationView | null; onCreateConversation: (title: string) => Promise<ConversationView>; onStreamingChange: (id: string, isStreaming: boolean) => void; onSessionExpired: () => void }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toolSelectionMessage, setToolSelectionMessage] = useState<string | null>(null)
  const [responsePerformance, setResponsePerformance] = useState<ResponsePerformance | null>(null)
  const selectedConversationIdRef = useRef<string | null>(conversation?.id ?? null)
  const streamControllersRef = useRef(new Map<string, AbortController>())
  const streamSessionsRef = useRef(new Map<string, StreamSession>())
  const messageRevisionRef = useRef(new Map<string, number>())
  selectedConversationIdRef.current = conversation?.id ?? null

  const conversationId = conversation?.id ?? null
  const conversationStatus = conversation?.status ?? null
  const isStreaming = conversation?.isStreaming ?? false

  useEffect(() => {
    setResponsePerformance(null)
    if (conversationId === null) { setMessages([]); setError(null); setToolSelectionMessage(null); setLoading(false); return }
    const session = streamSessionsRef.current.get(conversationId)
    setToolSelectionMessage(session?.toolSelectionMessage ?? null)
    if (conversationStatus === 'created') {
      setMessages(session ? previewForCreatedConversation(session) : [])
      setError(session?.error ?? null)
      if (session?.completed && session.error !== null) streamSessionsRef.current.delete(conversationId)
      setLoading(false)
      return
    }

    const requestRevision = messageRevisionRef.current.get(conversationId) ?? 0
    const controller = new AbortController(); setLoading(true); setError(session?.error ?? null)
    void listMessages(conversationId).then((items) => {
      const currentRevision = messageRevisionRef.current.get(conversationId) ?? 0
      if (controller.signal.aborted || currentRevision !== requestRevision) return
      const latestSession = streamSessionsRef.current.get(conversationId)
      setMessages(latestSession ? mergeStreamSession(items, latestSession) : items)
      setError(latestSession?.error ?? null)
      if (latestSession?.completed && latestSession.error !== null) streamSessionsRef.current.delete(conversationId)
    }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired()
      else setError(reason instanceof Error ? reason.message : '메시지를 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [conversationId, conversationStatus, onSessionExpired])

  useEffect(() => () => {
    for (const controller of streamControllersRef.current.values()) controller.abort()
  }, [])

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const prompt = draft.trim()
    if (!prompt || isStreaming) return

    setError(null)
    setResponsePerformance(null)
    let activeConversationId = conversation?.id ?? null
    let createdConversationId: string | null = null
    let streamStarted = false
    let cancelled = false
    const pendingSuffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const pendingUserId = `pending-user-${pendingSuffix}`
    const pendingAssistantId = `pending-assistant-${pendingSuffix}`
    const isVisible = () => selectedConversationIdRef.current === activeConversationId

    try {
      if (activeConversationId === null) {
        createdConversationId = (await onCreateConversation(titleFrom(prompt))).id
        activeConversationId = createdConversationId
      }

      const session: StreamSession = {
        userMessage: { id: pendingUserId, role: 'user', content: prompt, created_at: new Date().toISOString() },
        assistantMessage: { id: pendingAssistantId, role: 'assistant', content: '', created_at: new Date().toISOString() },
        toolSelectionMessage: null,
        error: null,
        completed: false,
      }
      streamSessionsRef.current.set(activeConversationId, session)
      const currentRevision = messageRevisionRef.current.get(activeConversationId) ?? 0
      messageRevisionRef.current.set(activeConversationId, currentRevision + 1)
      if (createdConversationId === activeConversationId) setMessages(previewForCreatedConversation(session))
      else if (isVisible()) setMessages((current) => mergeStreamSession(current, session))
      if (createdConversationId === activeConversationId || isVisible()) setToolSelectionMessage(null)

      const controller = new AbortController()
      streamControllersRef.current.set(activeConversationId, controller)
      onStreamingChange(activeConversationId, true)

      let streamFailed = false
      const requestStartedAt = performance.now()
      let firstDeltaAt: number | null = null
      let lastDeltaAt: number | null = null
      await streamMessage(activeConversationId, prompt, (streamEvent) => {
        if (streamEvent.event === 'tool_selected') {
          session.toolSelectionMessage = streamEvent.data.message
          if (isVisible()) setToolSelectionMessage(streamEvent.data.message)
        }
        if (streamEvent.event === 'data') {
          session.toolSelectionMessage = null
          if (isVisible()) setToolSelectionMessage(null)
          const receivedAt = performance.now()
          firstDeltaAt ??= receivedAt
          lastDeltaAt = receivedAt
          session.assistantMessage.content += streamEvent.data
          if (isVisible()) setMessages((current) => current.some((item) => item.id === pendingAssistantId)
            ? current.map((item) => item.id === pendingAssistantId ? { ...item, content: session.assistantMessage.content } : item)
            : mergeStreamSession(current.filter((item) => item.id !== pendingUserId), session))
        }
        if (streamEvent.event === 'error') {
          streamFailed = true
          session.error = streamEvent.data
          session.toolSelectionMessage = null
          if (isVisible()) { setError(streamEvent.data); setToolSelectionMessage(null) }
        }
        if (streamEvent.event === 'done') {
          session.toolSelectionMessage = null
          if (isVisible()) setToolSelectionMessage(null)
          const generationMs = firstDeltaAt === null || lastDeltaAt === null
            ? null
            : lastDeltaAt - firstDeltaAt
          const generationTokensPerSecond = generationMs !== null && generationMs > 0
            ? streamEvent.data.usage.output_tokens / (generationMs / 1_000)
            : null
          if (isVisible()) {
            setResponsePerformance({
              usage: streamEvent.data.usage,
              ttftMs: firstDeltaAt === null ? null : firstDeltaAt - requestStartedAt,
              generationTokensPerSecond,
            })
          }
        }
      }, controller.signal, () => { streamStarted = true })

      if (streamFailed) {
        session.completed = true
        session.assistantMessage.content = ''
      }
      if (!streamFailed && isVisible()) setDraft('')
      const completedRevision = messageRevisionRef.current.get(activeConversationId) ?? 0
      messageRevisionRef.current.set(activeConversationId, completedRevision + 1)
      const saved = await listMessages(activeConversationId)
      if (isVisible()) setMessages(saved)
      if (!streamFailed || isVisible()) streamSessionsRef.current.delete(activeConversationId)
    } catch (reason) {
      cancelled = reason instanceof DOMException && reason.name === 'AbortError'
      if (cancelled) {
        if (activeConversationId !== null) streamSessionsRef.current.delete(activeConversationId)
        if (isVisible()) setToolSelectionMessage(null)
        return
      }
      if (reason instanceof InvalidDoneUsageError && activeConversationId !== null && streamStarted) {
        const completedRevision = messageRevisionRef.current.get(activeConversationId) ?? 0
        messageRevisionRef.current.set(activeConversationId, completedRevision + 1)
        streamSessionsRef.current.delete(activeConversationId)
        try {
          const saved = await listMessages(activeConversationId)
          if (isVisible()) setMessages(saved)
        } catch (reloadReason) {
          if (reloadReason instanceof ApiError && reloadReason.status === 401) onSessionExpired()
          else if (isVisible()) setError(reloadReason instanceof Error ? reloadReason.message : '메시지를 불러오지 못했습니다.')
        }
        return
      }
      if (reason instanceof ApiError && reason.status === 401) {
        cancelled = true
        onSessionExpired()
      }
      else if (isVisible()) setError(reason instanceof Error ? reason.message : '메시지를 전송하지 못했습니다.')

      const streamError = reason instanceof Error ? reason.message : '메시지를 전송하지 못했습니다.'
      const session = activeConversationId === null ? null : streamSessionsRef.current.get(activeConversationId)
      if (session && streamStarted && activeConversationId !== null) {
        session.completed = true
        session.error ??= streamError
        session.assistantMessage.content = ''
        const failedRevision = messageRevisionRef.current.get(activeConversationId) ?? 0
        messageRevisionRef.current.set(activeConversationId, failedRevision + 1)
        if (isVisible()) streamSessionsRef.current.delete(activeConversationId)
      } else if (activeConversationId !== null) {
        streamSessionsRef.current.delete(activeConversationId)
      }

      if (isVisible()) {
        setToolSelectionMessage(null)
        const pendingIds = streamStarted ? [pendingAssistantId] : [pendingUserId, pendingAssistantId]
        setMessages((current) => current.filter((item) => !pendingIds.includes(item.id)))
      }
    } finally {
      if (activeConversationId !== null) {
        streamControllersRef.current.delete(activeConversationId)
        onStreamingChange(activeConversationId, false)
      }
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  const pendingMessage = toolSelectionMessage ?? '응답을 생성하고 있습니다'

  return <section className="chat" aria-label="대화"><header className="chat-header"><h1>{conversation === null ? '새 대화' : '대화'}</h1><p>{conversation === null ? '첫 메시지를 보내 대화를 시작하세요.' : '대화 기록과 응답이 여기에 표시됩니다.'}</p></header>
    <div className="message-list" aria-live="polite">
      {loading && <p className="chat-status">메시지를 불러오는 중…</p>}
      {!loading && messages.length === 0 && <p className="chat-status">무엇을 도와드릴까요?</p>}
      {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}><strong>{message.role === 'user' ? '나' : '어시스턴트'}</strong>{message.content ? <p>{message.content}</p> : isStreaming ? <p className="message-pending"><span className="visually-hidden">{pendingMessage}</span><span aria-hidden="true">{pendingMessage}</span><span className="message-pending-dots" aria-hidden="true"><span></span><span></span><span></span></span></p> : <p></p>}</article>)}
    </div>
    <footer className="composer-area">{responsePerformance && <section className="response-performance" aria-label="최근 응답 사용량 및 성능">
      <h2>최근 응답</h2>
      <dl>
        <div><dt>입력 토큰</dt><dd>{formatInteger(responsePerformance.usage.input_tokens)}</dd></div>
        <div><dt>출력 토큰</dt><dd>{formatInteger(responsePerformance.usage.output_tokens)}</dd></div>
        <div><dt>컨텍스트</dt><dd>{formatContextUsage(responsePerformance.usage)}</dd></div>
        <div><dt>TTFT</dt><dd>{formatTtft(responsePerformance.ttftMs)}</dd></div>
        <div><dt>생성 속도</dt><dd>{formatGenerationSpeed(responsePerformance.generationTokensPerSecond)}</dd></div>
      </dl>
    </section>}{error && <p className="chat-error" role="alert">{error}</p>}<form className="chat-composer" onSubmit={(event) => void send(event)}><label htmlFor="message">메시지</label><textarea id="message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="메시지를 입력하세요" maxLength={8000} rows={3} disabled={isStreaming} /><p className="composer-hint">Enter로 전송 · Shift + Enter로 줄바꿈</p><button className="primary-button" disabled={isStreaming || !draft.trim()}>{isStreaming ? '응답 생성 중…' : '보내기'}</button></form><p className="geocoding-attribution">위치 검색 데이터: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a></p></footer>
  </section>
}

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, listMessages } from '../lib/api'
import { streamMessage } from '../lib/sse'
import type { ConversationView, Message } from '../lib/types'
import './ChatView.css'

type DisplayMessage = Message | { id: string; role: 'assistant'; content: string; created_at: string }
type StreamSession = {
  userMessage: Message
  assistantMessage: Extract<DisplayMessage, { role: 'assistant' }>
  error: string | null
  completed: boolean
}

const titleFrom = (message: string) => Array.from(message).slice(0, 30).join('')

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
  const selectedConversationIdRef = useRef<string | null>(conversation?.id ?? null)
  const streamControllersRef = useRef(new Map<string, AbortController>())
  const streamSessionsRef = useRef(new Map<string, StreamSession>())
  const messageRevisionRef = useRef(new Map<string, number>())
  selectedConversationIdRef.current = conversation?.id ?? null

  const conversationId = conversation?.id ?? null
  const conversationStatus = conversation?.status ?? null
  const isStreaming = conversation?.isStreaming ?? false

  useEffect(() => {
    if (conversationId === null) { setMessages([]); setError(null); setLoading(false); return }
    const session = streamSessionsRef.current.get(conversationId)
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
      if (controller.signal.aborted || messageRevisionRef.current.get(conversationId) !== requestRevision) return
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
        error: null,
        completed: false,
      }
      streamSessionsRef.current.set(activeConversationId, session)
      const currentRevision = messageRevisionRef.current.get(activeConversationId) ?? 0
      messageRevisionRef.current.set(activeConversationId, currentRevision + 1)
      if (createdConversationId === activeConversationId) setMessages(previewForCreatedConversation(session))
      else if (isVisible()) setMessages((current) => mergeStreamSession(current, session))

      const controller = new AbortController()
      streamControllersRef.current.set(activeConversationId, controller)
      onStreamingChange(activeConversationId, true)

      let streamFailed = false
      await streamMessage(activeConversationId, prompt, (streamEvent) => {
        if (streamEvent.event === 'data') {
          session.assistantMessage.content += streamEvent.data
          if (isVisible()) setMessages((current) => current.some((item) => item.id === pendingAssistantId)
            ? current.map((item) => item.id === pendingAssistantId ? { ...item, content: session.assistantMessage.content } : item)
            : mergeStreamSession(current.filter((item) => item.id !== pendingUserId), session))
        }
        if (streamEvent.event === 'error') {
          streamFailed = true
          session.error = streamEvent.data
          if (isVisible()) setError(streamEvent.data)
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

  return <section className="chat" aria-label="대화"><header className="chat-header"><h1>{conversation === null ? '새 대화' : '대화'}</h1><p>{conversation === null ? '첫 메시지를 보내 대화를 시작하세요.' : '대화 기록과 응답이 여기에 표시됩니다.'}</p></header>
    <div className="message-list" aria-live="polite">
      {loading && <p className="chat-status">메시지를 불러오는 중…</p>}
      {!loading && messages.length === 0 && <p className="chat-status">무엇을 도와드릴까요?</p>}
      {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}><strong>{message.role === 'user' ? '나' : '어시스턴트'}</strong><p>{message.content || (isStreaming ? '응답을 생성하고 있습니다…' : '')}</p></article>)}
    </div>
    <footer className="composer-area">{error && <p className="chat-error" role="alert">{error}</p>}<form className="chat-composer" onSubmit={(event) => void send(event)}><label htmlFor="message">메시지</label><textarea id="message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="메시지를 입력하세요" maxLength={8000} rows={3} disabled={isStreaming} /><p className="composer-hint">Enter로 전송 · Shift + Enter로 줄바꿈</p><button className="primary-button" disabled={isStreaming || !draft.trim()}>{isStreaming ? '응답 생성 중…' : '보내기'}</button></form></footer>
  </section>
}

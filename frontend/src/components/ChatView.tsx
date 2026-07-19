import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, listMessages } from '../lib/api'
import { streamMessage } from '../lib/sse'
import type { Conversation, Message } from '../lib/types'
import './ChatView.css'

type DisplayMessage = Message | { id: string; role: 'assistant'; content: string; created_at: string }
const titleFrom = (message: string) => Array.from(message).slice(0, 30).join('')

export function ChatView({ conversationId, onCreateConversation, onConversationReady, onSessionExpired }: { conversationId: string | null; onCreateConversation: (title: string) => Promise<Conversation>; onConversationReady: (id: string) => void; onSessionExpired: () => void }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingConversationIds, setStreamingConversationIds] = useState<Set<string>>(() => new Set())
  const [newConversationStreaming, setNewConversationStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectedConversationIdRef = useRef<string | null>(conversationId)
  const streamControllersRef = useRef(new Map<string, AbortController>())
  const newConversationStreamIdRef = useRef<string | null>(null)
  selectedConversationIdRef.current = conversationId

  const isStreaming = conversationId === null ? newConversationStreaming : streamingConversationIds.has(conversationId)

  function setConversationStreaming(id: string, streaming: boolean) {
    setStreamingConversationIds((current) => {
      const next = new Set(current)
      if (streaming) next.add(id)
      else next.delete(id)
      return next
    })
  }

  useEffect(() => {
    if (conversationId === null) { setMessages([]); setError(null); setLoading(false); return }
    setNewConversationStreaming(false)
    const controller = new AbortController(); setLoading(true); setError(null)
    void listMessages(conversationId).then((items) => { if (!controller.signal.aborted) setMessages(items) }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired()
      else setError(reason instanceof Error ? reason.message : '메시지를 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [conversationId, onSessionExpired])

  useEffect(() => () => {
    for (const controller of streamControllersRef.current.values()) controller.abort()
  }, [])

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const prompt = draft.trim()
    if (!prompt || isStreaming) return

    setError(null)
    let activeConversationId = conversationId
    let createdConversationId: string | null = null
    let streamStarted = false
    let cancelled = false
    const pendingSuffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    const pendingUserId = `pending-user-${pendingSuffix}`
    const pendingAssistantId = `pending-assistant-${pendingSuffix}`

    try {
      if (activeConversationId === null) {
        createdConversationId = (await onCreateConversation(titleFrom(prompt))).id
        activeConversationId = createdConversationId
      }

      if (selectedConversationIdRef.current === activeConversationId) {
        const temporaryUser: Message = { id: pendingUserId, role: 'user', content: prompt, created_at: new Date().toISOString() }
        setMessages((current) => [...current, temporaryUser, { id: pendingAssistantId, role: 'assistant', content: '', created_at: new Date().toISOString() }])
      }

      const controller = new AbortController()
      streamControllersRef.current.set(activeConversationId, controller)
      setConversationStreaming(activeConversationId, true)
      if (conversationId === null) {
        newConversationStreamIdRef.current = activeConversationId
        setNewConversationStreaming(true)
      }

      let streamFailed = false
      await streamMessage(activeConversationId, prompt, (streamEvent) => {
        if (selectedConversationIdRef.current !== activeConversationId) return
        if (streamEvent.event === 'data') setMessages((current) => current.map((item) => item.id === pendingAssistantId ? { ...item, content: item.content + streamEvent.data } : item))
        if (streamEvent.event === 'error') { streamFailed = true; setError(streamEvent.data) }
      }, controller.signal, () => { streamStarted = true })

      if (!streamFailed && selectedConversationIdRef.current === activeConversationId) setDraft('')
      const saved = await listMessages(activeConversationId)
      if (selectedConversationIdRef.current === activeConversationId) setMessages(saved)
    } catch (reason) {
      cancelled = reason instanceof DOMException && reason.name === 'AbortError'
      if (cancelled) return
      if (reason instanceof ApiError && reason.status === 401) {
        cancelled = true
        onSessionExpired()
      }
      else if (selectedConversationIdRef.current === activeConversationId) setError(reason instanceof Error ? reason.message : '메시지를 전송하지 못했습니다.')

      if (selectedConversationIdRef.current === activeConversationId) {
        const pendingIds = streamStarted ? [pendingAssistantId] : [pendingUserId, pendingAssistantId]
        setMessages((current) => current.filter((item) => !pendingIds.includes(item.id)))
      }
    } finally {
      if (activeConversationId !== null) {
        streamControllersRef.current.delete(activeConversationId)
        setConversationStreaming(activeConversationId, false)
      }
      if (newConversationStreamIdRef.current === activeConversationId) {
        newConversationStreamIdRef.current = null
        setNewConversationStreaming(false)
      }
      if (createdConversationId !== null && !cancelled && selectedConversationIdRef.current === null) onConversationReady(createdConversationId)
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  return <section className="chat" aria-label="대화"><header className="chat-header"><h1>{conversationId === null ? '새 대화' : '대화'}</h1><p>{conversationId === null ? '첫 메시지를 보내 대화를 시작하세요.' : '대화 기록과 응답이 여기에 표시됩니다.'}</p></header>
    <div className="message-list" aria-live="polite">
      {loading && <p className="chat-status">메시지를 불러오는 중…</p>}
      {!loading && messages.length === 0 && <p className="chat-status">무엇을 도와드릴까요?</p>}
      {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}><strong>{message.role === 'user' ? '나' : '어시스턴트'}</strong><p>{message.content || (isStreaming ? '응답을 생성하고 있습니다…' : '')}</p></article>)}
    </div>
    <footer className="composer-area">{error && <p className="chat-error" role="alert">{error}</p>}<form className="chat-composer" onSubmit={(event) => void send(event)}><label htmlFor="message">메시지</label><textarea id="message" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="메시지를 입력하세요" maxLength={8000} rows={3} disabled={isStreaming} /><p className="composer-hint">Enter로 전송 · Shift + Enter로 줄바꿈</p><button className="primary-button" disabled={isStreaming || !draft.trim()}>{isStreaming ? '응답 생성 중…' : '보내기'}</button></form></footer>
  </section>
}

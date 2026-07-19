import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, listMessages } from '../lib/api'
import { streamMessage } from '../lib/sse'
import type { Conversation, Message } from '../lib/types'
import './ChatView.css'

type DisplayMessage = Message | { id: 'pending-assistant'; role: 'assistant'; content: string; created_at: string }
const titleFrom = (message: string) => Array.from(message).slice(0, 30).join('')

export function ChatView({ conversationId, onCreateConversation, onSessionExpired }: { conversationId: string | null; onCreateConversation: (title: string) => Promise<Conversation>; onSessionExpired: () => void }) {
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    abortRef.current?.abort()
    if (conversationId === null) { setMessages([]); setError(null); setLoading(false); return }
    const controller = new AbortController(); setLoading(true); setError(null)
    void listMessages(conversationId).then((items) => { if (!controller.signal.aborted) setMessages(items) }).catch((reason: unknown) => {
      if (controller.signal.aborted) return
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired()
      else setError(reason instanceof Error ? reason.message : '메시지를 불러오지 못했습니다.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [conversationId, onSessionExpired])

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const prompt = draft.trim()
    if (!prompt || streaming) return
    setError(null)
    let activeConversationId = conversationId
    try {
      if (activeConversationId === null) activeConversationId = (await onCreateConversation(titleFrom(prompt))).id
      const temporaryUser: Message = { id: `pending-user-${Date.now()}`, role: 'user', content: prompt, created_at: new Date().toISOString() }
      setMessages((current) => [...current, temporaryUser, { id: 'pending-assistant', role: 'assistant', content: '', created_at: new Date().toISOString() }])
      setStreaming(true)
      const controller = new AbortController(); abortRef.current = controller
      let streamFailed = false
      await streamMessage(activeConversationId, prompt, (streamEvent) => {
        if (streamEvent.event === 'data') setMessages((current) => current.map((item) => item.id === 'pending-assistant' ? { ...item, content: item.content + streamEvent.data } : item))
        if (streamEvent.event === 'error') { streamFailed = true; setError(streamEvent.data) }
      }, controller.signal)
      if (!streamFailed) setDraft('')
      const saved = await listMessages(activeConversationId)
      setMessages(saved)
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === 'AbortError') return
      if (reason instanceof ApiError && reason.status === 401) onSessionExpired()
      else setError(reason instanceof Error ? reason.message : '메시지를 전송하지 못했습니다.')
      setMessages((current) => current.filter((item) => item.id !== 'pending-assistant'))
    } finally { setStreaming(false); abortRef.current = null }
  }

  return <section className="chat" aria-label="대화"><header className="chat-header"><h1>{conversationId === null ? '새 대화' : '대화'}</h1><p>{conversationId === null ? '첫 메시지를 보내 대화를 시작하세요.' : '대화 기록과 응답이 여기에 표시됩니다.'}</p></header>
    <div className="message-list" aria-live="polite">
      {loading && <p className="chat-status">메시지를 불러오는 중…</p>}
      {!loading && messages.length === 0 && <p className="chat-status">무엇을 도와드릴까요?</p>}
      {messages.map((message) => <article className={`message message-${message.role}`} key={message.id}><strong>{message.role === 'user' ? '나' : '어시스턴트'}</strong><p>{message.content || (streaming ? '응답을 생성하고 있습니다…' : '')}</p></article>)}
    </div>
    <footer className="composer-area">{error && <p className="chat-error" role="alert">{error}</p>}<form className="chat-composer" onSubmit={(event) => void send(event)}><label htmlFor="message">메시지</label><textarea id="message" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="메시지를 입력하세요" maxLength={8000} rows={3} disabled={streaming} /><button className="primary-button" disabled={streaming || !draft.trim()}>{streaming ? '응답 생성 중…' : '보내기'}</button></form></footer>
  </section>
}

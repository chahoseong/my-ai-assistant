import { useCallback, useEffect, useState } from 'react'
import { AuthView } from './components/AuthView'
import { ChatView } from './components/ChatView'
import { ConversationSidebar } from './components/ConversationSidebar'
import {
  ApiError,
  createConversation,
  getCurrentUser,
  listConversations,
  logout,
} from './lib/api'
import type { Conversation, PublicUser } from './lib/types'
import './App.css'

type SessionState =
  | { kind: 'checking' }
  | { kind: 'anonymous' }
  | { kind: 'authenticated'; user: PublicUser }

function App() {
  const [session, setSession] = useState<SessionState>({ kind: 'checking' })
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)

  const becomeAnonymous = useCallback(() => {
    setSession({ kind: 'anonymous' })
    setConversations([])
    setSelectedConversationId(null)
  }, [])

  const loadConversations = useCallback(async () => {
    setListError(null)
    try {
      const items = await listConversations()
      setConversations(items)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        becomeAnonymous()
        return
      }
      setListError(error instanceof Error ? error.message : '대화 목록을 불러오지 못했습니다.')
    }
  }, [becomeAnonymous])

  useEffect(() => {
    void (async () => {
      try {
        const user = await getCurrentUser()
        setSession({ kind: 'authenticated', user })
        await loadConversations()
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          becomeAnonymous()
          return
        }
        setSession({ kind: 'anonymous' })
      }
    })()
  }, [becomeAnonymous, loadConversations])

  const handleAuthenticated = useCallback(async () => {
    const user = await getCurrentUser()
    setSession({ kind: 'authenticated', user })
    await loadConversations()
  }, [loadConversations])

  const handleLogout = useCallback(async () => {
    try {
      await logout()
    } finally {
      becomeAnonymous()
    }
  }, [becomeAnonymous])

  const handleCreateConversation = useCallback(async (title: string) => {
    try {
      const conversation = await createConversation(title)
      setConversations((current) => [conversation, ...current])
      return conversation
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        becomeAnonymous()
      }
      throw error
    }
  }, [becomeAnonymous])

  if (session.kind === 'checking') {
    return <main className="session-status">세션을 확인하고 있습니다…</main>
  }

  if (session.kind === 'anonymous') {
    return <AuthView onAuthenticated={handleAuthenticated} />
  }

  return (
    <main className="application-shell">
      <ConversationSidebar
        conversations={conversations}
        error={listError}
        selectedConversationId={selectedConversationId}
        username={session.user.username}
        onNewConversation={() => setSelectedConversationId(null)}
        onRefresh={() => void loadConversations()}
        onSelect={setSelectedConversationId}
        onLogout={() => void handleLogout()}
      />
      <ChatView
        conversationId={selectedConversationId}
        onCreateConversation={handleCreateConversation}
        onConversationReady={setSelectedConversationId}
        onSessionExpired={becomeAnonymous}
      />
    </main>
  )
}

export default App

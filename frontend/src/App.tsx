import { useCallback, useEffect, useState } from 'react'
import { AuthView } from './components/AuthView'
import { ChatView } from './components/ChatView'
import {
  ConversationSidebar,
  type DeleteConversationResult,
} from './components/ConversationSidebar'
import {
  ApiError,
  createConversation,
  deleteConversation,
  getCurrentUser,
  listConversations,
  logout,
} from './lib/api'
import type { ConversationView, PublicUser } from './lib/types'
import './App.css'

type SessionState =
  | { kind: 'checking' }
  | { kind: 'anonymous' }
  | { kind: 'authenticated'; user: PublicUser }

function withHiddenStatus(conversation: ConversationView): ConversationView {
  return { ...conversation, status: 'hidden' }
}

function App() {
  const [session, setSession] = useState<SessionState>({ kind: 'checking' })
  const [conversations, setConversations] = useState<ConversationView[]>([])
  const [listError, setListError] = useState<string | null>(null)
  const activeConversation = conversations.find((conversation) => conversation.status !== 'hidden') ?? null

  const becomeAnonymous = useCallback(() => {
    setSession({ kind: 'anonymous' })
    setConversations([])
  }, [])

  const loadConversations = useCallback(async () => {
    setListError(null)
    try {
      const items = await listConversations()
      setConversations((current) => {
        const active = current.find((conversation) => conversation.status !== 'hidden')
        return items.map((item) => {
          const previous = current.find((conversation) => conversation.id === item.id)
          return {
            ...item,
            status: active?.id === item.id ? active.status : 'hidden',
            isStreaming: previous?.isStreaming ?? false,
          }
        })
      })
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

  const handleCreateConversation = useCallback(async (title: string): Promise<ConversationView> => {
    try {
      const conversation = await createConversation(title)
      const view: ConversationView = { ...conversation, status: 'created', isStreaming: false }
      setConversations((current) => [view, ...current.map(withHiddenStatus)])
      return view
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        becomeAnonymous()
      }
      throw error
    }
  }, [becomeAnonymous])

  const handleSelectConversation = useCallback((id: string) => {
    setConversations((current) => current.map((conversation) => ({
      ...conversation,
      status: conversation.id === id ? 'displayed' : 'hidden',
    })))
  }, [])

  const handleNewConversation = useCallback(() => {
    setConversations((current) => current.map(withHiddenStatus))
  }, [])

  const removeConversation = useCallback((id: string) => {
    setConversations((current) => current.filter((conversation) => conversation.id !== id))
  }, [])

  const handleDeleteConversation = useCallback(async (id: string): Promise<DeleteConversationResult> => {
    try {
      await deleteConversation(id)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        becomeAnonymous()
        return { kind: 'removed' }
      }
      if (error instanceof ApiError && error.status === 404) {
        removeConversation(id)
        return { kind: 'removed' }
      }
      if (error instanceof ApiError && error.status === 409) {
        return { kind: 'blocked', message: error.message }
      }
      throw error
    }

    removeConversation(id)
    return { kind: 'removed' }
  }, [becomeAnonymous, removeConversation])

  const handleStreamingChange = useCallback((id: string, isStreaming: boolean) => {
    setConversations((current) => current.map((conversation) => (
      conversation.id === id ? { ...conversation, isStreaming } : conversation
    )))
  }, [])

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
        selectedConversationId={activeConversation?.id ?? null}
        username={session.user.username}
        onDelete={handleDeleteConversation}
        onNewConversation={handleNewConversation}
        onRefresh={() => void loadConversations()}
        onSelect={handleSelectConversation}
        onLogout={() => void handleLogout()}
      />
      <ChatView
        conversation={activeConversation}
        onCreateConversation={handleCreateConversation}
        onStreamingChange={handleStreamingChange}
        onSessionExpired={becomeAnonymous}
      />
    </main>
  )
}

export default App

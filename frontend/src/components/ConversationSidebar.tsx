import { useState } from 'react'
import type { Conversation } from '../lib/types'
import './ConversationSidebar.css'

function titleFor(conversation: Conversation) {
  return conversation.title ?? new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(conversation.created_at))
}

export type DeleteConversationResult =
  | { kind: 'removed' }
  | { kind: 'blocked'; message: string }

type ConversationSidebarProps = {
  conversations: Conversation[]
  selectedConversationId: string | null
  username: string
  error: string | null
  onDelete: (id: string) => Promise<DeleteConversationResult>
  onNewConversation: () => void
  onSelect: (id: string) => void
  onRefresh: () => void
  onLogout: () => void
}

export function ConversationSidebar(props: ConversationSidebarProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [deleteNotice, setDeleteNotice] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  async function handleDelete(conversation: Conversation) {
    const title = titleFor(conversation)
    const confirmed = window.confirm(
      `"${title}" 대화를 영구 삭제할까요?\n삭제한 대화는 복구할 수 없습니다.`,
    )
    if (!confirmed) return

    setDeletingId(conversation.id)
    setDeleteNotice(null)
    setDeleteError(null)
    try {
      const result = await props.onDelete(conversation.id)
      if (result.kind === 'blocked') setDeleteNotice(result.message)
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : '대화를 삭제하지 못했습니다.',
      )
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <aside className="sidebar" aria-label="대화 목록">
      <header>
        <p className="eyebrow">LOCAL ASSISTANT</p>
        <strong>{props.username}</strong>
      </header>
      <button className="new-conversation" type="button" onClick={props.onNewConversation}>
        + 새 대화
      </button>
      <div className="conversation-list">
        {props.error && <div className="sidebar-error" role="alert"><p>{props.error}</p><button type="button" onClick={props.onRefresh}>다시 시도</button></div>}
        {deleteNotice && <p className="sidebar-notice" role="status">{deleteNotice}</p>}
        {deleteError && <p className="sidebar-error" role="alert">{deleteError}</p>}
        {!props.error && props.conversations.length === 0 && <p className="empty-list">아직 대화가 없습니다.</p>}
        {props.conversations.map((conversation) => {
          const title = titleFor(conversation)
          const isDeleting = deletingId === conversation.id
          return <div className="conversation-item" key={conversation.id}>
            <button className="conversation-link" type="button" aria-current={conversation.id === props.selectedConversationId ? 'page' : undefined} onClick={() => props.onSelect(conversation.id)}>{title}</button>
            <button className="delete-conversation" type="button" aria-label={`${title} 삭제`} disabled={isDeleting} onClick={() => void handleDelete(conversation)}>{isDeleting ? '삭제 중…' : '삭제'}</button>
          </div>
        })}
      </div>
      <button className="logout-button" type="button" onClick={props.onLogout}>로그아웃</button>
    </aside>
  )
}

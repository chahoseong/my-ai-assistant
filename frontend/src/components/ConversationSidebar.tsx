import type { Conversation } from '../lib/types'
import './ConversationSidebar.css'

function titleFor(conversation: Conversation) {
  return conversation.title ?? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(conversation.created_at))
}

export function ConversationSidebar(props: {
  conversations: Conversation[]; selectedConversationId: string | null; username: string; error: string | null
  onNewConversation: () => void; onSelect: (id: string) => void; onRefresh: () => void; onLogout: () => void
}) {
  return <aside className="sidebar" aria-label="대화 목록"><header><p className="eyebrow">LOCAL ASSISTANT</p><strong>{props.username}</strong></header>
    <button className="new-conversation" onClick={props.onNewConversation}>+ 새 대화</button>
    <div className="conversation-list">
      {props.error && <div className="sidebar-error" role="alert"><p>{props.error}</p><button onClick={props.onRefresh}>다시 시도</button></div>}
      {!props.error && props.conversations.length === 0 && <p className="empty-list">아직 대화가 없습니다.</p>}
      {props.conversations.map((conversation) => <button key={conversation.id} className="conversation-link" aria-current={conversation.id === props.selectedConversationId ? 'page' : undefined} onClick={() => props.onSelect(conversation.id)}>{titleFor(conversation)}</button>)}
    </div>
    <button className="logout-button" onClick={props.onLogout}>로그아웃</button>
  </aside>
}

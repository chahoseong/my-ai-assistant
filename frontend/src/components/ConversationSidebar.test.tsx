import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ConversationSidebar } from './ConversationSidebar'

const conversation = {
  id: 'conversation-1',
  title: '삭제할 대화',
  created_at: '2026-07-24T00:00:00.000Z',
}

function renderSidebar(onDelete = vi.fn()) {
  return render(
    <ConversationSidebar
      conversations={[conversation]}
      selectedConversationId={conversation.id}
      username="tester"
      error={null}
      onDelete={onDelete}
      onNewConversation={vi.fn()}
      onRefresh={vi.fn()}
      onSelect={vi.fn()}
      onLogout={vi.fn()}
    />,
  )
}

describe('ConversationSidebar deletion controls', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('confirms before requesting deletion', async () => {
    const onDelete = vi.fn().mockResolvedValue({ kind: 'removed' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSidebar(onDelete)

    fireEvent.click(screen.getByRole('button', { name: '삭제할 대화 삭제' }))

    expect(window.confirm).toHaveBeenCalledOnce()
    expect(onDelete).toHaveBeenCalledWith('conversation-1')
  })

  it('announces a streaming conflict without treating it as an error', async () => {
    const onDelete = vi.fn().mockResolvedValue({
      kind: 'blocked',
      message: '응답 생성 중에는 삭제할 수 없습니다',
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSidebar(onDelete)

    fireEvent.click(screen.getByRole('button', { name: '삭제할 대화 삭제' }))

    expect(await screen.findByRole('status')).toHaveTextContent(
      '응답 생성 중에는 삭제할 수 없습니다',
    )
  })
})

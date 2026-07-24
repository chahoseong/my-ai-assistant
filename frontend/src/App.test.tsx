import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

const user = {
  id: 'user-1',
  username: 'tester',
  created_at: '2026-07-24T00:00:00.000Z',
}

const conversation = {
  id: 'conversation-1',
  title: '삭제할 대화',
  created_at: '2026-07-24T00:00:00.000Z',
}

function jsonResponse(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('App conversation deletion', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('clears the active conversation after a successful deletion', async () => {
    const fetchMock = vi.fn(async (input: string | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/api/auth/me') return jsonResponse(user)
    if (path === '/api/conversations/conversation-1' && init?.method === 'DELETE') {
        return new Response(null, { status: 204 })
      }
      if (path === '/api/conversations') return jsonResponse([conversation])
      if (path === '/api/conversations/conversation-1/messages') return jsonResponse([])
      throw new Error(`Unexpected request: ${path}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    render(<App />)

    const selectButton = await screen.findByRole('button', { name: '삭제할 대화' })
    fireEvent.click(selectButton)
    await screen.findByRole('heading', { name: '대화' })

    fireEvent.click(screen.getByRole('button', { name: '삭제할 대화 삭제' }))

    await screen.findByRole('heading', { name: '새 대화' })
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '삭제할 대화' })).not.toBeInTheDocument()
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/conversations/conversation-1', {
      credentials: 'same-origin',
      method: 'DELETE',
    })
  })
})

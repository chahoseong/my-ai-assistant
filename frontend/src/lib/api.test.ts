import { afterEach, describe, expect, it, vi } from 'vitest'
import * as api from './api'

describe('deleteConversation', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('accepts a 204 response without attempting JSON parsing', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      (api as typeof api & { deleteConversation: (id: string) => Promise<void> })
        .deleteConversation('conversation-1'),
    ).resolves.toBeUndefined()

    expect(fetchMock).toHaveBeenCalledWith('/api/conversations/conversation-1', {
      credentials: 'same-origin',
      method: 'DELETE',
    })
  })
})

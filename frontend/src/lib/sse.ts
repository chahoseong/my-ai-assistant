import { errorFrom, jsonRequest } from './api'

export type StreamEvent = { event: 'data' | 'done' | 'error'; data: string }

function consumeEvent(rawEvent: string): StreamEvent | null {
  let event = 'data'
  const data: string[] = []
  for (const line of rawEvent.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (data.length === 0 || !['data', 'done', 'error'].includes(event)) return null
  return { event: event as StreamEvent['event'], data: data.join('\n') }
}

export async function streamMessage(
  conversationId: string,
  message: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    credentials: 'same-origin',
    signal,
    ...jsonRequest({ message }),
  })
  if (!response.ok) throw await errorFrom(response)
  if (response.body === null) throw new Error('스트리밍 응답 본문이 없습니다.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replaceAll('\r\n', '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const event = consumeEvent(buffer.slice(0, boundary))
      if (event) onEvent(event)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
}

import { errorFrom, jsonRequest } from './api'
import type { StreamDoneData } from './types'

export type StreamEvent =
  | { event: 'data'; data: string }
  | { event: 'done'; data: StreamDoneData }
  | { event: 'error'; data: string }

export class InvalidDoneUsageError extends Error {
  constructor() {
    super('응답 사용량 형식이 올바르지 않습니다.')
    this.name = 'InvalidDoneUsageError'
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

const isNonNegativeInteger = (value: unknown): value is number =>
  typeof value === 'number' && Number.isInteger(value) && value >= 0

const isContextLimit = (value: unknown): value is number | null =>
  value === null || (typeof value === 'number' && Number.isInteger(value) && value > 0)

function parseDoneData(data: string): StreamDoneData {
  let body: unknown
  try {
    body = JSON.parse(data)
  } catch {
    throw new InvalidDoneUsageError()
  }

  if (!isRecord(body) || !isRecord(body.usage)) {
    throw new InvalidDoneUsageError()
  }

  const usage = body.usage
  if (
    !isNonNegativeInteger(usage.input_tokens)
    || !isNonNegativeInteger(usage.output_tokens)
    || !isContextLimit(usage.context_limit)
  ) {
    throw new InvalidDoneUsageError()
  }

  return {
    usage: {
      input_tokens: usage.input_tokens,
      output_tokens: usage.output_tokens,
      context_limit: usage.context_limit,
    },
  }
}

function consumeEvent(rawEvent: string): StreamEvent | null {
  let event = 'data'
  const data: string[] = []
  for (const line of rawEvent.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (data.length === 0 || !['data', 'done', 'error'].includes(event)) return null
  const value = data.join('\n')
  if (event === 'done') return { event: 'done', data: parseDoneData(value) }
  return { event: event as 'data' | 'error', data: value }
}

export async function streamMessage(
  conversationId: string,
  message: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  onStarted?: () => void,
) {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    credentials: 'same-origin',
    signal,
    ...jsonRequest({ message }),
  })
  if (!response.ok) throw await errorFrom(response)
  if (response.body === null) throw new Error('스트리밍 응답 본문이 없습니다.')
  onStarted?.()

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

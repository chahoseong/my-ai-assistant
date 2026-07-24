import type { Conversation, Message, PublicUser } from './types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let message = `요청에 실패했습니다. (${response.status})`
  try {
    const body: unknown = await response.json()
    if (typeof body === 'object' && body !== null && 'detail' in body && typeof body.detail === 'string') {
      message = body.detail
    }
  } catch {
    // JSON 오류 본문이 없는 응답도 위의 상태 메시지로 처리한다.
  }
  return new ApiError(response.status, message)
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { credentials: 'same-origin', ...init })
  if (!response.ok) throw await errorFrom(response)
  return (await response.json()) as T
}

export function getCurrentUser() { return request<PublicUser>('/api/auth/me') }
export function listConversations() { return request<Conversation[]>('/api/conversations') }
export function listMessages(id: string) { return request<Message[]>(`/api/conversations/${id}/messages`) }

export async function signup(username: string, password: string) {
  return request<PublicUser>('/api/auth/signup', jsonRequest({ username, password }))
}

export async function login(username: string, password: string) {
  const response = await fetch('/api/auth/login', { credentials: 'same-origin', ...jsonRequest({ username, password }) })
  if (!response.ok) throw await errorFrom(response)
}

export async function logout() {
  const response = await fetch('/api/auth/logout', { credentials: 'same-origin', method: 'POST' })
  if (!response.ok) throw await errorFrom(response)
}

export function createConversation(title: string) {
  return request<Conversation>('/api/conversations', jsonRequest({ title }))
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`/api/conversations/${id}`, {
    credentials: 'same-origin',
    method: 'DELETE',
  })
  if (!response.ok) throw await errorFrom(response)
}

export function jsonRequest(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export { errorFrom }

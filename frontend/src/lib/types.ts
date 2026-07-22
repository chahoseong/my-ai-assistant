export interface PublicUser {
  id: string
  username: string
  created_at: string
}

export interface Conversation {
  id: string
  title: string | null
  created_at: string
}

export type ConversationStatus = 'created' | 'displayed' | 'hidden'

export interface ConversationView extends Conversation {
  status: ConversationStatus
  isStreaming: boolean
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ResponseUsage {
  input_tokens: number
  output_tokens: number
  context_limit: number | null
}

export interface StreamDoneData {
  usage: ResponseUsage
}

import { useState, type FormEvent } from 'react'
import { login, signup } from '../lib/api'
import './AuthView.css'

type Mode = 'login' | 'signup'

export function AuthView({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null); setNotice(null); setSubmitting(true)
    try {
      if (mode === 'signup') {
        await signup(username, password)
        setMode('login'); setPassword(''); setNotice('계정이 생성되었습니다. 로그인해 주세요.')
      } else {
        await login(username, password)
        await onAuthenticated()
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '요청을 처리하지 못했습니다.')
    } finally { setSubmitting(false) }
  }

  return <main className="auth-page"><section className="auth-card">
    <p className="eyebrow">LOCAL ASSISTANT</p><h1>{mode === 'login' ? '다시 오셨군요' : '계정을 만드세요'}</h1>
    <div className="tabs" role="tablist" aria-label="인증 방식">
      <button role="tab" aria-selected={mode === 'login'} onClick={() => { setMode('login'); setError(null); setNotice(null) }}>로그인</button>
      <button role="tab" aria-selected={mode === 'signup'} onClick={() => { setMode('signup'); setError(null); setNotice(null) }}>회원가입</button>
    </div>
    <form onSubmit={(event) => void submit(event)}>
      <label>사용자 이름<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>
      <label>비밀번호<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" minLength={15} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required /></label>
      {mode === 'signup' && <p className="hint">비밀번호는 15~128자여야 합니다.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}{notice && <p className="form-notice" role="status">{notice}</p>}
      <button className="primary-button" disabled={submitting}>{submitting ? '처리 중…' : mode === 'login' ? '로그인' : '계정 만들기'}</button>
    </form>
  </section></main>
}

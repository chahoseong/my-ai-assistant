# Frontend Design: Minimal Assistant UI

## Purpose and Scope

Provide a practical browser UI for the existing assistant APIs: signup, login,
conversation selection, message history, new-conversation creation, streamed
assistant responses, and logout. The UI is a support tool for backend learning,
not a separate frontend architecture exercise.

The design deliberately excludes tool-call UI, pagination, editing or deleting
conversations, dark mode, mobile-specific optimization, frontend automated
tests, and deployment.

## Architecture

The `frontend/` project uses React 19.2, Vite 8.1, and TypeScript 6.x. It has
no router, global state store, or SSE library.

`App` owns the small application state machine:

- `checking-session`: call `GET /api/auth/me` when the app starts.
- `anonymous`: render the authentication view after a 401.
- `authenticated`: render the conversation sidebar and chat view.

Presentation responsibilities are split into focused components:

- `AuthView`: signup/login tabs, submitted credentials, and server messages.
- `ConversationSidebar`: conversation list, selection, and the new-conversation
  action.
- `ChatView`: persisted history, message composer, stream progress, and errors.
- `lib/api`: cookie-aware JSON API requests and a consistent 401 signal.
- `lib/sse`: POST streaming response parsing with chunk-safe buffering.

This composition keeps authentication, list selection, and streaming state out
of one monolithic component while avoiding extra client libraries.

## Browser and Security Contract

Vite runs at `http://127.0.0.1:5173` and proxies `/api` to
`http://127.0.0.1:8000`. Requests use `credentials: "same-origin"`; the browser
therefore treats the API as the same origin during development.

The frontend never stores a password or session token in JavaScript state,
localStorage, or sessionStorage. The server-owned httpOnly cookie is the only
session credential. A 401 from a protected API clears in-memory authenticated
state and returns the UI to the login view.

Unsafe requests continue to be protected by the existing backend Origin policy.
The local backend runbook will allow exactly `http://127.0.0.1:5173`; this is
not a CORS relaxation. The UI renders all message content as plain React text,
not HTML.

## Data Flow

1. Start: `/api/auth/me` selects the anonymous or authenticated app state.
2. Authentication: signup creates an account; a successful signup returns to
   the login tab. Login sets the server session cookie, after which the app
   reloads the current user and conversations.
3. Listing: `GET /api/conversations` supplies the latest-first sidebar. A null
   title is displayed as its creation time.
4. Reading: selecting a conversation calls
   `GET /api/conversations/{id}/messages`; a cancelled or stale response cannot
   replace the newest selection.
5. Existing conversation: a POST stream appends data deltas to a temporary
   assistant message. `done` completes it; `error` shows an error; a 409 leaves
   the existing stream and unsent draft intact.
6. New conversation: clicking “New conversation” only changes UI state. The
   first non-blank message creates the conversation with the first 30 Unicode
   code points as its title, then streams that same message.

## Error and Empty States

Every fetch path distinguishes loading, empty, error, and data states. Server
`detail` messages are shown without replacing them with invented client text.
For a stream, HTTP errors are handled before reading the body, and SSE `error`
events are handled after the stream starts. A generated response failure keeps
the server-persisted user message visible so the user can retry.

## Accessibility and Visual Direction

The desktop-first layout has a semantic sidebar and main chat region. Native
buttons and labelled form controls provide keyboard access. Status/error text
uses appropriate live/status semantics and does not rely only on color.

Styles use a restrained neutral palette, consistent spacing, readable message
roles, visible focus indicators, and plain text rendering. The scope does not
promise bespoke mobile layouts, but the layout must not create a blank or
unusable page at ordinary desktop widths.

## Verification

- `npm run build` validates TypeScript and the production bundle.
- Browser verification covers signup/login, refresh persistence, conversation
  isolation, history loading, delta streaming, 409, SSE error, and logout.
- Backend verification keeps `GET /api/conversations` covered by ownership,
  ordering, authentication, error-safety, and OpenAPI-inventory tests.

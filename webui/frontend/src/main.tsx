import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App.tsx'
import { installDemoRuntime } from './lib/demo/demoMockInference'
import { isDemoMode } from './lib/demo/mode'
import './index.css'

if (isDemoMode()) {
  installDemoRuntime()
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

/** Last-resort error boundary: a render crash shows a recoverable panel
 * instead of a blank page. */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
          <h1 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>
            Something went wrong
          </h1>
          <p style={{ opacity: 0.8, marginBottom: '1rem' }}>
            The interface hit an unexpected error. Reloading usually fixes it.
          </p>
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              background: 'rgba(127,127,127,0.15)',
              padding: '0.75rem',
              borderRadius: '0.5rem',
              marginBottom: '1rem',
            }}
          >
            {this.state.error.message}
          </pre>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>,
)

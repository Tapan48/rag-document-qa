import { useEffect, useState } from 'react'

import { api } from '@/lib/api'

export function useRegistrationConfig() {
  const [state, setState] = useState<'loading' | 'enabled' | 'disabled' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    api.authConfig().then((config) => {
      if (cancelled) return
      if (typeof config.registration_enabled !== 'boolean') {
        setState('error')
        return
      }
      setState(config.registration_enabled ? 'enabled' : 'disabled')
    }).catch(() => {
      if (!cancelled) setState('error')
    })
    return () => { cancelled = true }
  }, [])

  return state
}

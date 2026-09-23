import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export function useRegistrationConfig() {
  const [state, setState] = useState<'loading' | 'enabled' | 'approval' | 'disabled' | 'error'>('loading')
  useEffect(() => {
    let cancelled = false
    api.authConfig().then((config) => {
      if (cancelled) return
      if (config.registration_mode === 'approval') setState('approval')
      else if (config.registration_mode === 'closed') setState('disabled')
      else if (config.registration_mode === 'open') setState('enabled')
      else if (typeof config.registration_enabled === 'boolean') setState(config.registration_enabled ? 'enabled' : 'disabled')
      else setState('error')
    }).catch(() => { if (!cancelled) setState('error') })
    return () => { cancelled = true }
  }, [])
  return state
}

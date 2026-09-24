export function safeWebUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password && !/\s/.test(url)
  } catch { return false }
}


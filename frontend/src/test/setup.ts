import '@testing-library/jest-dom/vitest'

// jsdom doesn't implement ResizeObserver, which Radix UI's ScrollArea (and
// a few other primitives) rely on.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (!('ResizeObserver' in globalThis)) {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver
}

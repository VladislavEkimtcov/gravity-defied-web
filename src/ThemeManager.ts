export type ThemeMode = 'auto' | 'dark' | 'light'

const STORAGE_KEY = 'color-scheme'
const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)'

export class ThemeManager {
  static readonly MODES: readonly ThemeMode[] = ['auto', 'dark', 'light']
  static readonly LABELS: string[] = ['Auto', 'On', 'Off']

  private mode: ThemeMode
  private readonly mediaQuery: MediaQueryList | null
  private readonly listeners = new Set<() => void>()

  constructor() {
    this.mediaQuery =
      typeof window !== 'undefined' && typeof window.matchMedia === 'function'
        ? window.matchMedia(DARK_MEDIA_QUERY)
        : null
    this.mode = this.readStoredMode()
    this.applyMeta()

    if (this.mediaQuery !== null) {
      this.mediaQuery.addEventListener('change', () => {
        if (this.mode === 'auto') {
          this.notifyListeners()
        }
      })
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('storage', (event: StorageEvent) => {
        if (event.key !== null && event.key !== STORAGE_KEY) {
          return
        }

        const nextMode = event.key === STORAGE_KEY ? this.parseMode(event.newValue) : this.readStoredMode()
        const prevIsDark = this.isDark()
        const modeChanged = nextMode !== this.mode
        this.mode = nextMode
        this.applyMeta()

        if (modeChanged || this.isDark() !== prevIsDark) {
          this.notifyListeners()
        }
      })
    }
  }

  getMode(): ThemeMode {
    return this.mode
  }

  getModeIndex(): number {
    const index = ThemeManager.MODES.indexOf(this.mode)
    return index === -1 ? 0 : index
  }

  setModeIndex(index: number): void {
    const nextMode = ThemeManager.MODES[index] ?? 'auto'
    this.persistMode(nextMode)

    const prevIsDark = this.isDark()
    const modeChanged = nextMode !== this.mode
    this.mode = nextMode
    this.applyMeta()

    if (modeChanged || this.isDark() !== prevIsDark) {
      this.notifyListeners()
    }
  }

  isDark(): boolean {
    if (this.mode === 'dark') {
      return true
    }
    if (this.mode === 'light') {
      return false
    }
    return this.mediaQuery?.matches ?? false
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener)
    return () => {
      this.listeners.delete(listener)
    }
  }

  private parseMode(value: string | null): ThemeMode {
    if (value === 'dark' || value === 'light') {
      return value
    }
    return 'auto'
  }

  private readStoredMode(): ThemeMode {
    try {
      if (typeof localStorage === 'undefined') {
        return 'auto'
      }
      return this.parseMode(localStorage.getItem(STORAGE_KEY))
    } catch {
      return 'auto'
    }
  }

  private persistMode(mode: ThemeMode): void {
    try {
      if (typeof localStorage === 'undefined') {
        return
      }
      if (mode === 'auto') {
        localStorage.removeItem(STORAGE_KEY)
      } else {
        localStorage.setItem(STORAGE_KEY, mode)
      }
    } catch {
      // Ignore storage errors (e.g. blocked site data / private mode).
    }
  }

  private applyMeta(): void {
    if (typeof document === 'undefined') {
      return
    }
    const meta = document.querySelector('meta[name="color-scheme"]')
    if (meta instanceof HTMLMetaElement) {
      meta.content = this.mode === 'auto' ? 'light dark' : this.mode
    }
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      listener()
    }
  }
}

export const themeManager = new ThemeManager()

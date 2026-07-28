const RECOVERY_STORAGE_KEY = "apm:preload-recovery-at";
const RECOVERY_COOLDOWN_MS = 60_000;

export interface PreloadRecoveryEnvironment {
  now: () => number;
  readLastAttempt: () => string | null;
  writeLastAttempt: (value: string) => void;
  reload: () => void;
}

function browserEnvironment(): PreloadRecoveryEnvironment {
  return {
    now: () => Date.now(),
    readLastAttempt: () => window.sessionStorage.getItem(RECOVERY_STORAGE_KEY),
    writeLastAttempt: (value) => window.sessionStorage.setItem(RECOVERY_STORAGE_KEY, value),
    reload: () => window.location.reload(),
  };
}

export function recoverFromPreloadError(
  event: Event,
  environment: PreloadRecoveryEnvironment = browserEnvironment(),
): boolean {
  const now = environment.now();
  let previousAttempt: number | null = null;
  try {
    const stored = environment.readLastAttempt();
    if (stored !== null) {
      const parsed = Number(stored);
      previousAttempt = Number.isFinite(parsed) ? parsed : null;
    }
  } catch {
    return false;
  }

  if (
    previousAttempt !== null &&
    now - previousAttempt >= 0 &&
    now - previousAttempt < RECOVERY_COOLDOWN_MS
  ) {
    return false;
  }

  try {
    environment.writeLastAttempt(String(now));
  } catch {
    return false;
  }
  event.preventDefault();
  environment.reload();
  return true;
}

export function installPreloadErrorRecovery(): () => void {
  const handler: EventListener = (event) => {
    recoverFromPreloadError(event);
  };
  window.addEventListener("vite:preloadError", handler);
  return () => window.removeEventListener("vite:preloadError", handler);
}

import { defineConfig, devices } from '@playwright/test';

// Env-driven so the isolated E2E stack (frontend/scripts/e2e-stack.sh,
// docker-compose.e2e.yml — backend on :8001) can run Playwright against its
// own ports without colliding with the developer's day-to-day dev server
// (:5173) or "me" compose project (backend on :8000). Defaults below keep
// today's behaviour unchanged when the vars are unset.
const APP_PORT = process.env.E2E_APP_PORT ?? '5173';
const API_BASE_URL = process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `npm run dev -- --port ${APP_PORT}`,
    url: `http://localhost:${APP_PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // Los specs interceptan con `page.route()` filtrando por `url.port !== "5173"`
    // (o `E2E_APP_PORT` cuando está definido) — es decir asumen que el front
    // llama al backend por URL absoluta (:8000, o `E2E_API_BASE_URL`).
    // Un `.env.local` con `VITE_API_BASE_URL=` (cadena vacía) rompe ese supuesto:
    // `??` en src/api/client.ts solo cae al default con null/undefined, así que la
    // cadena vacía deja el baseURL relativo, las peticiones salen por el proxy de
    // Vite y ningún `page.route()` las intercepta. Fijar la variable aquí
    // hace la suite e2e autónoma sin tocar la configuración de desarrollo local.
    env: { VITE_API_BASE_URL: API_BASE_URL },
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Usa el binario chromium disponible en el entorno (sin descargar).
        // En CI/dev con red, el comportamiento por defecto descarga el shell.
        launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
          ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
          : undefined,
      },
    },
  ],
});

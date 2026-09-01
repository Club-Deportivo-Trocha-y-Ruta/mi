import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev -- --port 5173',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    // Los specs interceptan con `page.route()` filtrando por `url.port !== "5173"`,
    // es decir asumen que el front llama al backend por URL absoluta (:8000).
    // Un `.env.local` con `VITE_API_BASE_URL=` (cadena vacía) rompe ese supuesto:
    // `??` en src/api/client.ts solo cae al default con null/undefined, así que la
    // cadena vacía deja el baseURL relativo, las peticiones salen por el proxy de
    // Vite en :5173 y ningún `page.route()` las intercepta. Fijar la variable aquí
    // hace la suite e2e autónoma sin tocar la configuración de desarrollo local.
    env: { VITE_API_BASE_URL: 'http://localhost:8000' },
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

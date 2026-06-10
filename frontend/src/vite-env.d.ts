/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_RACE_MAX_PDF_MB?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/**
 * Build-time app version (commit SHA or package version) injected by Vite
 * `define` in vite.config.ts. Used by the query persister to scope/invalidate
 * the persisted cache per release. See feature 012.
 */
declare const __APP_VERSION__: string;

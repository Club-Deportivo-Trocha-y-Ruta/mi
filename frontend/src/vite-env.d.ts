/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_RACE_MAX_PDF_MB?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

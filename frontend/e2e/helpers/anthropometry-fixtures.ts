/**
 * Fixtures por API para los specs de captura antropométrica (feature 048).
 *
 * Cada spec crea sus PROPIOS deportistas sintéticos («Ficticio») en vez de
 * usar el atleta 1 del seed: los specs corren en paralelo y la regla
 * «una medición por fecha» (409 `anthropometry_same_date_exists`) haría
 * chocar dos archivos que midan al mismo deportista el mismo día.
 *
 * Limpieza: `cleanupAthlete` borra las mediciones que queden (DELETE, cascada
 * de pliegues y explicaciones IA) y archiva al deportista (soft delete; el
 * backend no ofrece borrado duro) para que no aparezca en listas ni en el
 * roster de las corridas siguientes.
 *
 * Datos 100 % sintéticos contra el stack e2e aislado (`scripts/e2e-stack.sh`).
 */
import { expect, type APIRequestContext } from '@playwright/test';

import { realTokens, type SeedRole } from './session';

export function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';
}

export async function authHeaders(
  request: APIRequestContext,
  role: SeedRole = 'coach',
): Promise<Record<string, string>> {
  const tokens = await realTokens(request, role);
  return { Authorization: `Bearer ${tokens.access_token}` };
}

export interface SyntheticAthlete {
  id: number;
  firstName: string;
  lastName: string;
  fullName: string;
}

/** Sufijo único por corrida y worker (evita choques de nombre en paralelo). */
export function uniqueSuffix(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1e6).toString(36)}`;
}

/**
 * Crea un deportista sintético del club del coach. Por defecto: niño de
 * ~12 años (elegible para pliegues, ≥ 9 años).
 */
export async function createSyntheticAthlete(
  request: APIRequestContext,
  opts: { firstName?: string; birthDate?: string; sex?: 'M' | 'F'; tag?: string } = {},
): Promise<SyntheticAthlete> {
  const headers = await authHeaders(request, 'coach');
  const meRes = await request.get(`${apiBaseUrl()}/api/auth/me`, { headers });
  expect(meRes.ok(), `GET /auth/me falló: ${meRes.status()}`).toBeTruthy();
  const me = (await meRes.json()) as { club_ids: number[] };
  const firstName = opts.firstName ?? 'Juan';
  const lastName = `Ficticio${opts.tag ?? ''}${uniqueSuffix()}`;
  const res = await request.post(`${apiBaseUrl()}/api/athletes`, {
    headers,
    data: {
      first_name: firstName,
      last_name: lastName,
      birth_date: opts.birthDate ?? '2014-05-10',
      sex: opts.sex ?? 'M',
      club_join_date: '2025-01-10',
      club_id: me.club_ids[0],
    },
  });
  expect(res.ok(), `creación de deportista sintético falló: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { id: number };
  return { id: body.id, firstName, lastName, fullName: `${firstName} ${lastName}` };
}

export interface RecordInput {
  evaluation_date: string;
  weight_kg: number;
  standing_height_cm: number;
  sitting_height_cm: number;
  arm_span_cm?: number | null;
}

export interface ApiRecord {
  id: number;
  evaluation_date: string;
  weight_kg: string | number;
  sitting_height_cm: string | number;
  maturation_status: string | null;
  can_modify?: boolean;
  plausibility_flags?: string[];
}

/** Crea una medición por API (el autor queda como `role`). */
export async function createRecord(
  request: APIRequestContext,
  athleteId: number,
  input: RecordInput,
  role: SeedRole = 'coach',
): Promise<ApiRecord> {
  const headers = await authHeaders(request, role);
  const res = await request.post(`${apiBaseUrl()}/api/athletes/${athleteId}/anthropometry`, {
    headers,
    data: { arm_span_cm: null, notes: null, ...input },
  });
  expect(res.status(), `creación de medición falló: ${res.status()}`).toBe(201);
  return (await res.json()) as ApiRecord;
}

export async function listRecords(
  request: APIRequestContext,
  athleteId: number,
  role: SeedRole = 'coach',
): Promise<ApiRecord[]> {
  const headers = await authHeaders(request, role);
  const res = await request.get(`${apiBaseUrl()}/api/athletes/${athleteId}/anthropometry`, {
    headers,
  });
  expect(res.ok(), `listado de mediciones falló: ${res.status()}`).toBeTruthy();
  return (await res.json()) as ApiRecord[];
}

/**
 * Borra todas las mediciones del deportista (admin: puede borrar las de
 * cualquier autor) y lo archiva. Tolerante a fallos: es limpieza.
 */
export async function cleanupAthlete(request: APIRequestContext, athleteId: number): Promise<void> {
  const admin = await authHeaders(request, 'admin');
  const listRes = await request.get(`${apiBaseUrl()}/api/athletes/${athleteId}/anthropometry`, {
    headers: admin,
  });
  if (listRes.ok()) {
    const records = (await listRes.json()) as ApiRecord[];
    for (const record of records) {
      await request.delete(`${apiBaseUrl()}/api/athletes/${athleteId}/anthropometry/${record.id}`, {
        headers: admin,
      });
    }
  }
  await request.delete(`${apiBaseUrl()}/api/athletes/${athleteId}`, {
    headers: admin,
    data: { reason_code: 'athlete_left_club' },
  });
}

/** YYYY-MM-DD local (mismo criterio que `todayISO` del frontend). */
export function localIso(date: Date = new Date()): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** YYYY-MM-DD de hace `days` días. */
export function daysAgoIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return localIso(d);
}

/** dd/mm/aaaa, como lo pinta el historial. */
export function toDisplayDate(iso: string): string {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

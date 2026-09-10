import type { Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

export interface AthleteCreate {
  first_name: string;
  last_name: string;
  birth_date: string;
  sex: Sex;
  club_join_date?: string | null;
  club_id: number;
}

export interface AthleteUpdate {
  first_name?: string;
  last_name?: string;
  club_join_date?: string | null;
}

/** Resuelto desde `users` (feature 041) — nunca un id crudo (FR-013). */
export interface AthleteArchivedByOut {
  user_id: number;
  display_name: string;
}

export interface AthleteOut {
  id: number;
  user_id: number;
  first_name: string;
  last_name: string;
  birth_date: string;
  sex: Sex;
  club_join_date: string | null;
  years_in_club: number | null;
  age_decimal: number | null;
  category: string | null;
  club_id: number;
  created_at: string;
  /**
   * Solo poblados para admin (`GET /api/athletes?include_archived=true`);
   * ausentes/`null` para coach y padre (contracts/athlete-archive.md §4).
   */
  deleted_at?: string | null;
  deleted_reason_code?: string | null;
  deleted_by?: AthleteArchivedByOut | null;
}

export interface AthleteDetailOut extends AthleteOut {
  latest_anthropometry: AnthropometricRecord | null;
}

export interface AthleteListOut {
  items: AthleteOut[];
  total: number;
}

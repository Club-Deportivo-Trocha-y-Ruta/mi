import type { Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

export interface AthleteCreate {
  first_name: string;
  last_name: string;
  birth_date: string;
  sex: Sex;
  years_in_club?: number | null;
  club_id: number;
}

export interface AthleteUpdate {
  first_name?: string;
  last_name?: string;
  years_in_club?: number | null;
}

export interface AthleteOut {
  id: number;
  user_id: number;
  first_name: string;
  last_name: string;
  birth_date: string;
  sex: Sex;
  years_in_club: number | null;
  age_decimal: number | null;
  category: string | null;
  club_id: number;
  created_at: string;
}

export interface AthleteDetailOut extends AthleteOut {
  latest_anthropometry: AnthropometricRecord | null;
}

export interface AthleteListOut {
  items: AthleteOut[];
  total: number;
}

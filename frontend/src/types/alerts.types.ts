export type MeasurementStatus = "overdue" | "due_soon" | "ok" | "never";

export type GrowthAlert = "rapid_growth" | "approaching_circa" | "phase_changed";

export interface AthleteAlert {
  athlete_id: number;
  athlete_name: string;
  sex: string;
  age_decimal: number;
  category: string;
  measurement_status: MeasurementStatus;
  last_measurement_date: string | null;
  next_due_date: string | null;
  days_overdue: number | null;
  current_phv_status: string | null;
  measurement_interval_days: number;
  growth_velocity_cm_month: number | null;
  growth_alerts: GrowthAlert[];
  training_implications: string | null;
}

export interface AlertsSummary {
  overdue: number;
  due_soon: number;
  ok: number;
  never_measured: number;
  rapid_growth_count: number;
  athletes: AthleteAlert[];
}

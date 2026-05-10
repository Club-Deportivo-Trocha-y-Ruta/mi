// ---------------------------------------------------------------------------
// Enums (string literal types — matching backend Pydantic enums)
// ---------------------------------------------------------------------------

export type EventType =
  | "training_session"
  | "competition"
  | "club_event"
  | "personal_training"
  | "group_training"
  | "rest_day";

export type EventStatus = "scheduled" | "confirmed" | "cancelled" | "completed";

export type AudienceType = "all_club" | "category" | "athlete_list" | "individual";

export type RSVPStatus = "pending" | "accepted" | "declined" | "tentative";

export type ActualAttendanceStatus = "unknown" | "attended" | "no_show" | "excused";

// ---------------------------------------------------------------------------
// EventData — discriminated union by event_type
// ---------------------------------------------------------------------------

export interface EventDataTrainingSession {
  training_session_id?: number;
}

export interface EventDataCompetition {
  city: string;
  race_category: "A" | "B" | "C";
  is_departmental: boolean;
}

export interface EventDataClubEvent {
  kind: "social" | "meeting" | "workshop";
  registration_url?: string;
}

export interface EventDataPersonalTraining {
  athlete_id: number;
  intensity: "low" | "medium" | "high";
}

export interface EventDataGroupTraining {
  intensity: "low" | "medium" | "high";
  group_size_max?: number;
}

export interface EventDataRestDay {
  scope: "club" | "category" | "athlete";
  reason?: string;
}

export type EventData =
  | EventDataTrainingSession
  | EventDataCompetition
  | EventDataClubEvent
  | EventDataPersonalTraining
  | EventDataGroupTraining
  | EventDataRestDay;

// ---------------------------------------------------------------------------
// Audience — discriminated union by audience_type
// ---------------------------------------------------------------------------

export interface AudienceAllClub {
  audience_type: "all_club";
  audience_value: Record<string, never>;
}

export interface AudienceCategory {
  audience_type: "category";
  audience_value: { category: string };
}

export interface AudienceAthleteList {
  audience_type: "athlete_list";
  audience_value: { athlete_ids: number[] };
}

export interface AudienceIndividual {
  audience_type: "individual";
  audience_value: { athlete_id: number };
}

export type Audience =
  | AudienceAllClub
  | AudienceCategory
  | AudienceAthleteList
  | AudienceIndividual;

// ---------------------------------------------------------------------------
// Calendar Event — list item (lightweight, for FullCalendar)
// ---------------------------------------------------------------------------

export interface CalendarEventListItem {
  id: number;
  title: string;
  start: string;         // ISO datetime
  end: string;           // ISO datetime
  allDay: boolean;       // camelCase — backend alias
  event_type: EventType;
  color_hex: string | null;
  extended_props: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Calendar Event — full detail (coach/admin view)
// ---------------------------------------------------------------------------

export interface CalendarEventRead {
  id: number;
  club_id: number;
  event_type: EventType;
  status: EventStatus;
  title: string;
  description: string | null;
  location: string | null;
  start: string;
  end: string;
  allDay: boolean;
  timezone: string;
  event_data: EventData | null;
  color_hex: string | null;
  created_by_user_id: number;
  created_at: string;
  updated_at: string;
  audiences: Audience[];
  extended_props: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Payloads for API calls
// ---------------------------------------------------------------------------

export interface EventCreatePayload {
  event_type: EventType;
  title: string;
  description?: string;
  location?: string;
  start_at: string;      // ISO datetime
  end_at: string;        // ISO datetime
  all_day?: boolean;
  timezone?: string;
  event_data?: EventData;
  color_hex?: string;
  audiences: Audience[];
}

export type EventUpdatePayload = Partial<Omit<EventCreatePayload, "event_type">>;

export interface RSVPPayload {
  athlete_id: number;
  rsvp_status: RSVPStatus;
}

// ---------------------------------------------------------------------------
// Event attendance
// ---------------------------------------------------------------------------

export interface EventAttendanceRead {
  id: number;
  event_id: number;
  athlete_id: number;
  rsvp_status: RSVPStatus;
  rsvp_at: string | null;
  rsvp_by_user_id: number | null;
  actual_status: ActualAttendanceStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Calendar filters (for API + Zustand store)
// ---------------------------------------------------------------------------

export interface CalendarFilters {
  from: string;
  to: string;
  event_types?: EventType[];
  athlete_id?: number | null;
  category?: string | null;
}

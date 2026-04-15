import { apiClient } from "@/api/client";
import type {
  MyAthleteOut,
  ParentAthleteCreate,
  ParentAthleteListOut,
  ParentAthleteOut,
  ParentInviteCreate,
  ParentInviteCreatedOut,
  ParentInviteOut,
} from "@/types/parent.types";
import type { UserListOut, UserOut } from "@/types/user.types";

// --- Parent users (coach manages) ---

export async function getParentUsers(params?: {
  club_id?: number;
}): Promise<UserListOut> {
  const response = await apiClient.get<UserListOut>("/api/users", {
    params: { role: "parent", ...params },
  });
  return response.data;
}

// --- Parent-Athlete relationships ---

export async function getParentAthletes(params?: {
  athlete_id?: number;
  parent_id?: number;
}): Promise<ParentAthleteListOut> {
  const response = await apiClient.get<ParentAthleteListOut>(
    "/api/parent-athletes",
    { params },
  );
  return response.data;
}

export async function createParentAthlete(
  payload: ParentAthleteCreate,
): Promise<ParentAthleteOut> {
  const response = await apiClient.post<ParentAthleteOut>(
    "/api/parent-athletes",
    payload,
  );
  return response.data;
}

export async function deleteParentAthlete(id: number): Promise<void> {
  await apiClient.delete(`/api/parent-athletes/${id}`);
}

// --- Invitations ---

export async function createParentInvite(
  payload: ParentInviteCreate,
): Promise<ParentInviteCreatedOut> {
  const response = await apiClient.post<ParentInviteCreatedOut>(
    "/api/parent-athletes/invite",
    payload,
  );
  return response.data;
}

export async function getParentInvites(
  athleteId: number,
): Promise<ParentInviteOut[]> {
  const response = await apiClient.get<ParentInviteOut[]>(
    "/api/parent-athletes/invites",
    { params: { athlete_id: athleteId } },
  );
  return response.data;
}

// --- Create parent user (coach) ---

export async function createParentUser(payload: {
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  password?: string | null;
  club_id: number;
}): Promise<UserOut> {
  const response = await apiClient.post<UserOut>("/api/users", {
    ...payload,
    role: "parent",
  });
  return response.data;
}

// --- Parent portal (self) ---

export async function getMyAthletes(): Promise<MyAthleteOut[]> {
  const response = await apiClient.get<MyAthleteOut[]>(
    "/api/parent-athletes/my-athletes",
  );
  return response.data;
}

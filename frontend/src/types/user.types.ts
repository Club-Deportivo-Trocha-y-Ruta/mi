import type { UserRole } from "@/types/enums";

export interface UserOut {
  id: number;
  email: string | null;
  first_name: string;
  last_name: string;
  phone: string | null;
  role: UserRole;
  is_active: boolean;
  can_login: boolean;
  created_at: string;
}

export interface UserListOut {
  items: UserOut[];
  total: number;
}

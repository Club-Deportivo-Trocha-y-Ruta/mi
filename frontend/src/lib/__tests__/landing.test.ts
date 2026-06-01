import { describe, it, expect } from "vitest";

import { landingPathForRole } from "@/lib/landing";
import { UserRole } from "@/types/enums";

describe("landingPathForRole", () => {
  it("envía a coach y admin al Dashboard", () => {
    expect(landingPathForRole(UserRole.coach)).toBe("/dashboard");
    expect(landingPathForRole(UserRole.admin)).toBe("/dashboard");
  });

  it("envía a padres a su panel de atletas", () => {
    expect(landingPathForRole(UserRole.parent)).toBe("/my-athletes");
  });

  it("usa Dashboard como destino por defecto cuando no hay rol resuelto", () => {
    expect(landingPathForRole(null)).toBe("/dashboard");
    expect(landingPathForRole(undefined)).toBe("/dashboard");
    expect(landingPathForRole(UserRole.athlete)).toBe("/dashboard");
  });
});

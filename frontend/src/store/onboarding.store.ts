import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { FamilyRelationship } from "@/types/enums";

type OnboardingRole = "parent" | "coach" | "athlete" | null;

interface OnboardingPrefill {
  parentUserId: number | null;
  firstName: string | null;
  lastName: string | null;
  phone: string | null;
  relationshipType: FamilyRelationship | null;
}

interface OnboardingState {
  currentStep: number;
  role: OnboardingRole;
  token: string | null;
  email: string | null;
  athleteName: string | null;
  clubName: string | null;
  prefill: OnboardingPrefill;
  formData: Record<string, unknown>;

  setStep: (step: number) => void;
  setTokenData: (data: {
    role: string;
    token: string;
    email: string;
    athleteName: string;
    clubName: string;
    prefill?: Partial<OnboardingPrefill>;
  }) => void;
  updateFormData: (data: Record<string, unknown>) => void;
  reset: () => void;
}

const emptyPrefill: OnboardingPrefill = {
  parentUserId: null,
  firstName: null,
  lastName: null,
  phone: null,
  relationshipType: null,
};

const initialState = {
  currentStep: 0,
  role: null as OnboardingRole,
  token: null,
  email: null,
  athleteName: null,
  clubName: null,
  prefill: emptyPrefill,
  formData: {},
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initialState,

      setStep: (step) => set({ currentStep: step }),

      setTokenData: ({ role, token, email, athleteName, clubName, prefill }) =>
        set({
          role: role as OnboardingRole,
          token,
          email,
          athleteName,
          clubName,
          prefill: { ...emptyPrefill, ...(prefill ?? {}) },
        }),

      updateFormData: (data) =>
        set((state) => ({
          formData: { ...state.formData, ...data },
        })),

      reset: () => set(initialState),
    }),
    {
      name: "trocha-onboarding",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

type OnboardingRole = "parent" | "coach" | "athlete" | null;

interface OnboardingState {
  currentStep: number;
  role: OnboardingRole;
  token: string | null;
  email: string | null;
  athleteName: string | null;
  clubName: string | null;
  formData: Record<string, unknown>;

  setStep: (step: number) => void;
  setTokenData: (data: {
    role: string;
    token: string;
    email: string;
    athleteName: string;
    clubName: string;
  }) => void;
  updateFormData: (data: Record<string, unknown>) => void;
  reset: () => void;
}

const initialState = {
  currentStep: 0,
  role: null as OnboardingRole,
  token: null,
  email: null,
  athleteName: null,
  clubName: null,
  formData: {},
};

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set) => ({
      ...initialState,

      setStep: (step) => set({ currentStep: step }),

      setTokenData: ({ role, token, email, athleteName, clubName }) =>
        set({
          role: role as OnboardingRole,
          token,
          email,
          athleteName,
          clubName,
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

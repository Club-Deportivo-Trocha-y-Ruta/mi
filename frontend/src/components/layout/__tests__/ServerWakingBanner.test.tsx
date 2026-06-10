import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { ServerWakingBanner } from "@/components/layout/ServerWakingBanner";
import { useServerWakingStore } from "@/store/serverWaking.store";

expect.extend(toHaveNoViolations);

describe("ServerWakingBanner", () => {
  beforeEach(() => {
    useServerWakingStore.getState().resetForTests();
  });

  afterEach(() => {
    useServerWakingStore.getState().resetForTests();
  });

  it("renders nothing when not waking", () => {
    const { container } = render(<ServerWakingBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the es-CO waking message (with diacritics) when waking", () => {
    useServerWakingStore.setState({ isWaking: true });
    render(<ServerWakingBanner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(
      screen.getByText(/El servidor está despertando/),
    ).toBeInTheDocument();
  });

  it("clears automatically when isWaking returns to false", () => {
    useServerWakingStore.setState({ isWaking: true });
    const { rerender } = render(<ServerWakingBanner />);
    expect(screen.queryByRole("status")).toBeInTheDocument();

    useServerWakingStore.setState({ isWaking: false });
    rerender(<ServerWakingBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("has no accessibility violations while waking", async () => {
    useServerWakingStore.setState({ isWaking: true });
    const { container } = render(<ServerWakingBanner />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

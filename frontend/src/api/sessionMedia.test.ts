import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import * as apiClient from "@/api/client";
import {
  uploadSessionMedia,
  deleteSessionMedia,
  updateSessionMedia,
  fetchSessionMedia,
} from "./sessionMedia";

const { apiClient: mockApi } = apiClient as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

describe("sessionMedia API", () => {
  beforeEach(() => {
    mockApi.get.mockReset();
    mockApi.post.mockReset();
    mockApi.patch.mockReset();
    mockApi.delete.mockReset();
  });

  it("uploadSessionMedia envía FormData con todos los campos requeridos", async () => {
    mockApi.post.mockResolvedValue({ data: { id: 99 } });
    const file = new File(["bytes"], "foto.jpg", { type: "image/jpeg" });

    await uploadSessionMedia(7, {
      file,
      media_type: "photo",
      athlete_ids: [1, 2, 3],
      consent_ack: true,
      caption: "Mi caption",
    });

    expect(mockApi.post).toHaveBeenCalledTimes(1);
    const [url, body, config] = mockApi.post.mock.calls[0];
    expect(url).toBe("/api/training-sessions/7/media");
    expect(body).toBeInstanceOf(FormData);

    const fd = body as FormData;
    expect(fd.get("media_type")).toBe("photo");
    expect(fd.get("athlete_ids")).toBe("1,2,3");
    expect(fd.get("consent_ack")).toBe("true");
    expect(fd.get("caption")).toBe("Mi caption");
    expect(fd.get("file")).toBeInstanceOf(File);

    expect(config.headers["Content-Type"]).toBe("multipart/form-data");
  });

  it("uploadSessionMedia omite caption cuando es vacío", async () => {
    mockApi.post.mockResolvedValue({ data: { id: 1 } });
    const file = new File(["x"], "f.png", { type: "image/png" });

    await uploadSessionMedia(1, {
      file,
      media_type: "photo",
      athlete_ids: [4],
      consent_ack: true,
    });

    const fd = mockApi.post.mock.calls[0][1] as FormData;
    expect(fd.get("caption")).toBeNull();
  });

  it("deleteSessionMedia llama DELETE en la ruta correcta", async () => {
    mockApi.delete.mockResolvedValue({ data: null });
    await deleteSessionMedia(5, 22);
    expect(mockApi.delete).toHaveBeenCalledWith(
      "/api/training-sessions/5/media/22",
    );
  });

  it("updateSessionMedia envía PATCH con payload JSON", async () => {
    mockApi.patch.mockResolvedValue({ data: { id: 10 } });
    await updateSessionMedia(2, 10, {
      caption: "actualizado",
      athlete_ids: [1, 5],
    });
    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/training-sessions/2/media/10",
      { caption: "actualizado", athlete_ids: [1, 5] },
    );
  });

  it("fetchSessionMedia consulta GET en la ruta correcta", async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    await fetchSessionMedia(33);
    expect(mockApi.get).toHaveBeenCalledWith("/api/training-sessions/33/media");
  });
});

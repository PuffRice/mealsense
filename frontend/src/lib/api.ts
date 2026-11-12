import type {
  Candidate,
  Daily,
  DoctorAccessRequest,
  DoctorAnalytics,
  DoctorHistory,
  DoctorStatus,
  Food,
  Meal,
  MealInput,
  User,
} from "./types";

let csrf = "";
export async function initCsrf() {
  const response = await fetch("/api/v1/auth/csrf/", {
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error("Cannot connect to MealSense server.");
  csrf = (await response.json()).csrfToken;
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method || "GET";
  if (method !== "GET" && !csrf) await initCsrf();
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body)
    headers.set("Content-Type", "application/json");
  if (method !== "GET") headers.set("X-CSRFToken", csrf);
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...init,
      headers,
      credentials: "same-origin",
    });
  } catch {
    throw new Error("Connection lost. Try again when online.");
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const first = Object.values(data)[0];
    throw new Error(
      typeof first === "string"
        ? first
        : Array.isArray(first)
          ? String(first[0])
          : data.error || "Request failed.",
    );
  }
  return data as T;
}
export const auth = {
  me: () => api<User>("/users/me/"),
  login: async (identifier: string, password: string) => {
    const user = await api<User>("/auth/login/", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    });
    await initCsrf();
    return user;
  },
  register: async (
    email: string,
    password: string,
    username: string,
    display_name: string,
    timezone: string,
    gender = "",
    date_of_birth: string | null = null,
  ) => {
    const user = await api<User>("/auth/register/", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        username,
        display_name,
        timezone,
        gender,
        date_of_birth,
      }),
    });
    await initCsrf();
    return user;
  },
  logout: () => api<void>("/auth/logout/", { method: "POST" }),
  update: (data: Partial<User>) =>
    api<User>("/users/me/", { method: "PATCH", body: JSON.stringify(data) }),
  uploadPicture: (picture: File) => {
    const body = new FormData();
    body.append("profile_picture", picture);
    return api<User>("/users/me/profile-picture/", {
      method: "POST",
      body,
    });
  },
  removePicture: () =>
    api<User>("/users/me/profile-picture/", { method: "DELETE" }),
  remove: (password: string) =>
    api<void>("/users/me/", {
      method: "DELETE",
      body: JSON.stringify({ password }),
    }),
};
export const mealsApi = {
  list: () => api<Meal[]>("/meals/"),
  create: (data: MealInput) =>
    api<Meal>("/meals/", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: MealInput) =>
    api<Meal>(`/meals/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  remove: (id: string) => api<void>(`/meals/${id}/`, { method: "DELETE" }),
  daily: (date: string) => api<Daily>(`/nutrition/daily/?date=${date}`),
  weekly: () => api<Daily[]>("/nutrition/weekly/"),
};
export const foodsApi = {
  list: (q = "") => api<Food[]>(`/foods/?q=${encodeURIComponent(q)}`),
  create: (data: Omit<Food, "id" | "source" | "is_sample">) =>
    api<Food>("/foods/", { method: "POST", body: JSON.stringify(data) }),
};
export const doctorAccessApi = {
  list: () => api<DoctorAccessRequest[]>("/doctor-access/requests/"),
  decide: (id: string, action: "approve" | "deny" | "revoke") =>
    api<DoctorAccessRequest>(`/doctor-access/requests/${id}/decision/`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
};
const doctorHeaders = (token: string) => ({
  "X-Doctor-Access-Token": token,
});
export const doctorPortalApi = {
  request: (identifier: string, doctor_name: string) =>
    api<{ token: string | null; message: string }>("/doctor-access/request/", {
      method: "POST",
      body: JSON.stringify({ identifier, doctor_name }),
    }),
  status: (token: string) =>
    api<DoctorStatus>("/doctor-access/view/status/", {
      headers: doctorHeaders(token),
    }),
  history: (token: string, from?: string, to?: string, offset = 0) => {
    const params = new URLSearchParams({
      limit: "100",
      offset: String(offset),
    });
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    return api<DoctorHistory>(`/doctor-access/view/history/?${params}`, {
      headers: doctorHeaders(token),
    });
  },
  analytics: (token: string, from?: string, to?: string) => {
    const params = new URLSearchParams();
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    return api<DoctorAnalytics>(`/doctor-access/view/analytics/?${params}`, {
      headers: doctorHeaders(token),
    });
  },
};
export async function uploadMealImage(image: File) {
  const body = new FormData();
  body.append("image", image);
  return api<{
    id: string;
    image_id: string;
    status: "completed" | "failed" | "unavailable";
    candidates: Candidate[];
    model_version?: string;
    error_code?: string;
    message: string;
  }>("/recognitions/", { method: "POST", body });
}

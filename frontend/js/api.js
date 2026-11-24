// Helpers for talking to the Central Data Hub API.

async function errorMessage(response, fallback) {
  const data = await response.json().catch(() => ({}));
  return data.detail || fallback;
}

// GET a public endpoint and return its JSON.
export async function getJson(url) {
  return (await fetch(url)).json();
}

// Call an endpoint that needs the admin session; throws with the server's message.
export async function adminFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (!response.ok) throw new Error(await errorMessage(response, "ไม่สามารถทำรายการได้"));
  return response.json();
}

// POST a multipart form (file uploads); throws with the server's message.
export async function uploadForm(url, formData, failureMessage) {
  const response = await fetch(url, { method: "POST", body: formData });
  if (!response.ok) throw new Error(await errorMessage(response, failureMessage));
  return response.json();
}

// { configured, authenticated } for the admin session; {} when it cannot be read.
export async function fetchAdminSession() {
  return fetch("/api/admin/session")
    .then((response) => (response.ok ? response.json() : {}))
    .catch(() => ({}));
}

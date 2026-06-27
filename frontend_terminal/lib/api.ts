const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8080').trim();

export function getApiBase(): string {
  return API_BASE_URL;
}

export function getWsLogsUrl(): string {
  const base = API_BASE_URL.replace(/^http/, 'ws');
  return `${base}/ws/logs`;
}

export function getWsStreamUrl(jobId: string): string {
  const base = API_BASE_URL.replace(/^http/, 'ws');
  return `${base}/ws/stream?jobId=${jobId}`;
}

export const api = {
  async get<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE_URL}${path}`);
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`GET ${path} failed (${res.status}): ${errText || res.statusText}`);
    }
    return res.json() as Promise<T>;
  },

  async post<T>(path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`POST ${path} failed (${res.status}): ${errText || res.statusText}`);
    }
    return res.json() as Promise<T>;
  },

  async delete<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE_URL}${path}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`DELETE ${path} failed (${res.status}): ${errText || res.statusText}`);
    }
    return res.json() as Promise<T>;
  },
};

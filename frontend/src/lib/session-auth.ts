const ACCESS_TOKEN_KEY = "finn-access-token";
const ACCESS_TOKEN_EVENT = "finn-access-token-changed";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(value: string): void {
  if (typeof window === "undefined") return;
  const token = value.trim();
  if (token) {
    window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
  } else {
    window.sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  }
  window.dispatchEvent(new Event(ACCESS_TOKEN_EVENT));
}

export function accessTokenHeaders(): Record<string, string> {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function subscribeToAccessToken(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(ACCESS_TOKEN_EVENT, callback);
  return () => window.removeEventListener(ACCESS_TOKEN_EVENT, callback);
}

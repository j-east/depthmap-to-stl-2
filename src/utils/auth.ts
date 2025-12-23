const STORAGE_KEY = 'openrouter_api_key';
const CODE_VERIFIER_KEY = 'pkce_code_verifier';

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const hash = await crypto.subtle.digest('SHA-256', data);
  const base64 = btoa(String.fromCharCode(...new Uint8Array(hash)));
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export function getStoredApiKey(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function isAuthenticated(): boolean {
  return getStoredApiKey() !== null;
}

export async function initiateLogin(): Promise<void> {
  const codeVerifier = generateRandomString(32);
  const codeChallenge = await generateCodeChallenge(codeVerifier);

  localStorage.setItem(CODE_VERIFIER_KEY, codeVerifier);

  const callbackUrl = window.location.origin + window.location.pathname;
  const authUrl = `https://openrouter.ai/auth?callback_url=${encodeURIComponent(callbackUrl)}&code_challenge=${codeChallenge}&code_challenge_method=S256`;

  console.log('Initiating login with callback URL:', callbackUrl);
  console.log('Auth URL:', authUrl);

  window.location.href = authUrl;
}

export async function handleCallback(): Promise<boolean> {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');

  if (!code) {
    return false;
  }

  const codeVerifier = localStorage.getItem(CODE_VERIFIER_KEY);

  if (!codeVerifier) {
    console.error('Code verifier not found');
    return false;
  }

  try {
    const response = await fetch('https://openrouter.ai/api/v1/auth/keys', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        code,
        code_verifier: codeVerifier,
        code_challenge_method: 'S256',
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to exchange code for API key');
    }

    const data = await response.json();

    if (data.key) {
      localStorage.setItem(STORAGE_KEY, data.key);
      localStorage.removeItem(CODE_VERIFIER_KEY);

      window.history.replaceState({}, document.title, window.location.pathname);

      return true;
    }

    return false;
  } catch (error) {
    console.error('Error during token exchange:', error);
    localStorage.removeItem(CODE_VERIFIER_KEY);
    return false;
  }
}

export function logout(): void {
  localStorage.removeItem(STORAGE_KEY);
  window.location.reload();
}

export interface AIDepthMapResponse {
  id: string;
  provider: string;
  model: string;
  object: string;
  created: number;
  choices: Array<{
    index: number;
    finish_reason: string;
    message: {
      role: string;
      content: string;
      reasoning?: string;
      images?: Array<{
        type: string;
        image_url: {
          url: string;
        };
        index: number;
      }>;
    };
  }>;
}

// PKCE helper functions
function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(new Uint8Array(hash));
}

function base64UrlEncode(array: Uint8Array): string {
  const base64 = btoa(String.fromCharCode(...array));
  return base64
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

// Store for PKCE state
const pkceStorage = {
  codeVerifier: null as string | null,
  accessToken: null as string | null,
};

export function initiatePKCEFlow(redirectUri: string = window.location.href.split('?')[0]): void {
  const codeVerifier = generateCodeVerifier();
  pkceStorage.codeVerifier = codeVerifier;

  // Store in sessionStorage as backup
  sessionStorage.setItem('pkce_code_verifier', codeVerifier);

  generateCodeChallenge(codeVerifier).then(codeChallenge => {
    const authUrl = new URL('https://openrouter.ai/auth');
    authUrl.searchParams.set('callback_url', redirectUri);
    authUrl.searchParams.set('code_challenge', codeChallenge);
    authUrl.searchParams.set('code_challenge_method', 'S256');

    // Open in new window or redirect
    window.location.href = authUrl.toString();
  });
}

export async function exchangeCodeForToken(code: string): Promise<string> {
  const codeVerifier = pkceStorage.codeVerifier || sessionStorage.getItem('pkce_code_verifier');

  if (!codeVerifier) {
    throw new Error('No code verifier found. Please restart the authentication flow.');
  }

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
    const errorText = await response.text();
    throw new Error(`Token exchange failed: ${response.status} ${response.statusText}\n${errorText}`);
  }

  const data = await response.json();
  const accessToken = data.api_key || data.key;

  // Store the access token
  pkceStorage.accessToken = accessToken;
  sessionStorage.setItem('openrouter_access_token', accessToken);

  // Clear the code verifier
  pkceStorage.codeVerifier = null;
  sessionStorage.removeItem('pkce_code_verifier');

  return accessToken;
}

export function getStoredAccessToken(): string | null {
  return pkceStorage.accessToken || sessionStorage.getItem('openrouter_access_token');
}

export function clearAccessToken(): void {
  pkceStorage.accessToken = null;
  sessionStorage.removeItem('openrouter_access_token');
}

export async function generateAIDepthMap(
  imageFile: File,
  accessToken?: string,
  apiEndpoint: string = 'https://openrouter.ai/api/v1/chat/completions'
): Promise<string> {
  // Use provided token or get from storage
  const token = accessToken || getStoredAccessToken();

  if (!token) {
    throw new Error('No access token available. Please authenticate first.');
  }

  // Convert image to base64
  const base64Image = await fileToBase64(imageFile);

  const requestBody = {
    model: 'google/gemini-3-pro-image-preview',
    messages: [
      {
        role: 'user',
        content: [
          {
            type: 'image_url',
            image_url: {
              url: base64Image
            }
          },
          {
            type: 'text',
            text: 'Generate a depth map with strong subject separation in the foreground with maximum depth detail and contrast. The background should have smooth, gradual depth transitions with minimal fine detail. Emphasize depth discontinuities at subject boundaries. Treat the primary subject (person/face) as the focal point with the sharpest depth gradients, while compressing background depth range.'
          }
        ]
      }
    ]
  };

  const response = await fetch(apiEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'HTTP-Referer': window.location.origin,
      'X-Title': 'Depthmap to STL Converter',
    },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API request failed: ${response.status} ${response.statusText}\n${errorText}`);
  }

  const data: AIDepthMapResponse = await response.json();

  // Extract the image from the response
  // Check if there are images in the message
  if (data.choices?.[0]?.message?.images?.[0]?.image_url?.url) {
    return data.choices[0].message.images[0].image_url.url;
  }

  // Fallback: check if content has image data
  if (data.choices?.[0]?.message?.content) {
    // If content contains a data URI, return it
    if (data.choices[0].message.content.startsWith('data:image/')) {
      return data.choices[0].message.content;
    }
  }

  throw new Error('No image data found in API response');
}

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export async function loadImageFromDataUrl(dataUrl: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = dataUrl;
  });
}

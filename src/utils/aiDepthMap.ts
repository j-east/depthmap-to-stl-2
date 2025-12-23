import { getStoredApiKey } from './auth';

const DEPTH_MAP_PROMPT = `Generate a depth map with strong subject separation. in the foreground with maximum depth detail and contrast. The background should have smooth, gradual depth transitions with minimal fine detail. Emphasize depth discontinuities at subject boundaries. Treat the primary subject (person/face) as the focal point with the sharpest depth gradients, while compressing background depth range.`;

export interface AIDepthMapResult {
  imageUrl: string;
  message: string;
}

export async function generateDepthMapFromImage(
  imageFile: File
): Promise<AIDepthMapResult> {
  const apiKey = getStoredApiKey();

  if (!apiKey) {
    throw new Error('Not authenticated. Please login with OpenRouter.');
  }

  // Convert image to base64
  const base64Image = await fileToBase64(imageFile);

  try {
    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        'HTTP-Referer': window.location.origin,
        'X-Title': 'DepthMap to STL',
      },
      body: JSON.stringify({
        model: 'google/gemini-2.0-flash-exp:free',
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image_url',
                image_url: {
                  url: base64Image,
                },
              },
              {
                type: 'text',
                text: DEPTH_MAP_PROMPT,
              },
            ],
          },
        ],
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error?.message || `API request failed: ${response.status}`);
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;

    if (!content) {
      throw new Error('No content in response');
    }

    // Extract image URL from markdown if present
    const imageUrlMatch = content.match(/!\[.*?\]\((.*?)\)/);
    if (imageUrlMatch) {
      return {
        imageUrl: imageUrlMatch[1],
        message: content,
      };
    }

    // Check if content is a direct URL
    if (content.startsWith('http')) {
      return {
        imageUrl: content,
        message: 'Generated depth map',
      };
    }

    throw new Error('No image URL found in response: ' + content);
  } catch (error) {
    console.error('Error generating depth map:', error);
    throw error;
  }
}

async function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

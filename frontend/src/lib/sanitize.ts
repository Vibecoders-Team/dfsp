export function sanitizeFilename(name?: string): string {
  if (!name) return '';
  const withoutCtrl = removeControlChars(name);
  const cleaned = withoutCtrl.replace(/[<>:"'`\\/|?*]/g, '_');
  const trimmed = cleaned.trim();
  return trimmed || 'file';
}

/**
 * Parse Content-Disposition header to extract filename
 * Handles both filename and filename* (RFC 5987) parameters
 * @param header Content-Disposition header value
 * @returns extracted filename or null
 */
export function parseContentDisposition(header?: string | null): string | null {
  if (!header) return null;

  // Try filename* (RFC 5987) first - supports UTF-8 encoding
  const filenameStarMatch = header.match(/filename\*=UTF-8''(.+?)(?:;|$)/i);
  if (filenameStarMatch) {
    try {
      return decodeURIComponent(filenameStarMatch[1]);
    } catch (e) {
      console.warn('Failed to decode filename*:', e);
    }
  }

  // Try regular filename parameter with quotes
  const filenameQuotedMatch = header.match(/filename="(.+?)"/i);
  if (filenameQuotedMatch) {
    return filenameQuotedMatch[1];
  }

  // Try regular filename parameter without quotes
  const filenameMatch = header.match(/filename=([^;]+)/i);
  if (filenameMatch) {
    return filenameMatch[1].trim();
  }

  return null;
}

export function safeText(value?: string): string {
  if (!value) return '';
  return removeControlChars(value).trim();
}

function removeControlChars(s: string): string {
  // remove ASCII control characters (0x00-0x1F) and DEL (0x7F)
  let out = '';
  for (let i = 0; i < s.length; i++) {
    const code = s.charCodeAt(i);
    if ((code >= 0x20 && code !== 0x7f) || code > 0x7f) {
      out += s.charAt(i);
    }
  }
  return out;
}

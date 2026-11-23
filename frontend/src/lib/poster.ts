import { getApiOrigin } from "@/lib/api";

const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL?.replace("/api/v1", "")
  ?? "http://127.0.0.1:8000")
  .replace(/^http:\/\/localhost(?=:)/, "http://127.0.0.1");

/**
 * Normalize a poster image_url from the API into a browser-loadable URL.
 * - Absolute URLs (http/https) → returned as-is
 * - Relative paths → prefixed with API origin
 * - Avoids double-slash or double hostname issues
 */
export function getPosterImageUrl(imageUrl: string): string {
  if (!imageUrl) return "";
  if (imageUrl.startsWith("http://") || imageUrl.startsWith("https://")) {
    const parsed = new URL(imageUrl);
    if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
      return `${getApiOrigin() || API_ORIGIN}${parsed.pathname}${parsed.search}`;
    }
    return imageUrl;
  }
  // Relative path: prefix with origin
  const path = imageUrl.startsWith("/") ? imageUrl : `/${imageUrl}`;
  return `${getApiOrigin() || API_ORIGIN}${path}`;
}

/** True when the provider is mock — a transparent pixel, not a real image. */
export function isMockPoster(provider: string): boolean {
  return provider === "mock";
}

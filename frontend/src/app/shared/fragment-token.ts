/** Parses a `token=...` value out of a URL fragment (e.g. `#token=abc123`).
 * Fragments are never sent to the server on the initial request, unlike
 * query strings — this is why verification/reset links use `#token=`
 * instead of `?token=`. */
export function extractTokenFromFragment(fragment: string | null): string | null {
  if (!fragment) {
    return null;
  }
  const params = new URLSearchParams(fragment);
  return params.get('token');
}

import { extractTokenFromFragment } from './fragment-token';

describe('extractTokenFromFragment', () => {
  it('returns null when the fragment is null', () => {
    expect(extractTokenFromFragment(null)).toBeNull();
  });

  it('returns null when the fragment is empty', () => {
    expect(extractTokenFromFragment('')).toBeNull();
  });

  it('extracts the token value from a token=... fragment', () => {
    expect(extractTokenFromFragment('token=abc123')).toBe('abc123');
  });

  it('returns null when the fragment does not contain a token key', () => {
    expect(extractTokenFromFragment('foo=bar')).toBeNull();
  });
});

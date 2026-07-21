// Must share the frontend's hostname ("localhost"), not its IP form
// ("127.0.0.1"): the session/CSRF cookies are SameSite=Strict, and browsers
// treat "localhost" and "127.0.0.1" as different sites even though both
// resolve to the loopback interface.
export const API_BASE_URL = 'http://localhost:8000/api/v1';

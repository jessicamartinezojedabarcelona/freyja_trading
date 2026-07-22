import { environment } from '../../../environments/environment';

// In development, must share the frontend's hostname ("localhost"), not its
// IP form ("127.0.0.1"): the session/CSRF cookies are SameSite=Strict, and
// browsers treat "localhost" and "127.0.0.1" as different sites even though
// both resolve to the loopback interface. In production this is swapped via
// Angular's fileReplacements (angular.json) to environment.prod.ts.
export const API_BASE_URL = environment.apiBaseUrl;

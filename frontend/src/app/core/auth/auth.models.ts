export interface AuthUser {
  id: string;
  identifier: string;
}

export interface StatusResponse {
  status: string;
  message?: string;
}

export interface CsrfTokenResponse {
  status: string;
  csrf_token: string;
}

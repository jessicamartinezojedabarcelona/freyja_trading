import { Routes } from '@angular/router';

import { authGuard } from './core/auth/auth.guard';

export const routes: Routes = [
  {
    // Public landing page.
    path: '',
    pathMatch: 'full',
    loadComponent: () => import('./features/landing/landing.page').then((m) => m.LandingPage),
  },
  {
    path: 'login',
    loadComponent: () => import('./features/login/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'register',
    loadComponent: () => import('./features/register/register.page').then((m) => m.RegisterPage),
  },
  {
    path: 'forgot-password',
    loadComponent: () =>
      import('./features/forgot-password/forgot-password.page').then((m) => m.ForgotPasswordPage),
  },
  {
    path: 'reset-password',
    loadComponent: () =>
      import('./features/reset-password/reset-password.page').then((m) => m.ResetPasswordPage),
  },
  {
    // Everything behind the session shares one layout (brand, navigation, account).
    path: '',
    loadComponent: () => import('./features/app-shell/app-shell').then((m) => m.AppShell),
    canActivate: [authGuard],
    children: [
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage),
      },
      {
        path: 'mercados',
        loadComponent: () => import('./features/markets/markets.page').then((m) => m.MarketsPage),
      },
      {
        path: 'mercados/:instrumentId',
        loadComponent: () => import('./features/markets/markets.page').then((m) => m.MarketsPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];

import { Component, HostListener, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { Brand } from '../../shared/brand/brand';

interface NavLink {
  label: string;
  path: string;
  icon: 'dashboard' | 'markets';
}

/** Layout of every screen behind the session: brand, main navigation, the areas
 * that are still to come (visible but locked), the account, and the page itself.
 * On a phone the navigation slides in from the left. */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, Brand],
  templateUrl: './app-shell.html',
  styleUrl: './app-shell.scss',
})
export class AppShell {
  private readonly authService = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly user = this.authService.currentUser;
  protected readonly menuOpen = signal(false);

  /** Screens that exist today. */
  protected readonly links: readonly NavLink[] = [
    { label: 'Dashboard', path: '/dashboard', icon: 'dashboard' },
    { label: 'Mercados', path: '/mercados', icon: 'markets' },
  ];

  /** Areas from the information architecture (UX-IA-001) that are not built yet.
   * They stay visible and locked so nobody wonders where they went. */
  protected readonly upcoming: readonly string[] = [
    'Oportunidades',
    'Estrategias',
    'Operaciones',
    'Riesgo y cartera',
    'Backtesting',
    'Analítica',
  ];

  protected toggleMenu(): void {
    this.menuOpen.update((open) => !open);
  }

  @HostListener('document:keydown.escape')
  protected closeMenu(): void {
    this.menuOpen.set(false);
  }

  protected logout(): void {
    this.authService.logout().subscribe(() => void this.router.navigateByUrl('/login'));
  }
}

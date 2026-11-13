import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import * as useAuthModule from '../../hooks/useAuth';

vi.mock('../../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

function renderWithRouter(ui, initialRoute = '/protected') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
        <Route path="/change-password" element={<div data-testid="change-password-page">Change Password Page</div>} />
        <Route path="/dashboard" element={<div data-testid="dashboard-page">Dashboard Page</div>} />
        <Route path="/admin" element={<div data-testid="admin-page">Admin Page</div>} />
        <Route path="/super-admin" element={<div data-testid="super-admin-page">Super Admin Page</div>} />
        <Route path="/protected" element={ui} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading spinner when auth is loading', () => {
    useAuthModule.useAuth.mockReturnValue({
      loading: true,
      isAuthenticated: false,
      user: null,
      role: null,
      must_change_password: false,
    });

    const { container } = renderWithRouter(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>
    );

    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument();
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('redirects to /login when unauthenticated', () => {
    useAuthModule.useAuth.mockReturnValue({
      loading: false,
      isAuthenticated: false,
      user: null,
      role: null,
      must_change_password: false,
    });

    renderWithRouter(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>
    );

    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument();
    expect(screen.getByTestId('login-page')).toBeInTheDocument();
  });

  it('redirects to /change-password if must_change_password is true', () => {
    useAuthModule.useAuth.mockReturnValue({
      loading: false,
      isAuthenticated: true,
      user: { id: 'u1', role: 'student' },
      role: 'student',
      must_change_password: true,
    });

    renderWithRouter(
      <ProtectedRoute>
        <div>Secret Content</div>
      </ProtectedRoute>
    );

    expect(screen.queryByText('Secret Content')).not.toBeInTheDocument();
    expect(screen.getByTestId('change-password-page')).toBeInTheDocument();
  });

  it('redirects unauthorized role to their default dashboard', () => {
    useAuthModule.useAuth.mockReturnValue({
      loading: false,
      isAuthenticated: true,
      user: { id: 'u1', role: 'student' },
      role: 'student',
      must_change_password: false,
    });

    // Student trying to access admin-only route
    renderWithRouter(
      <ProtectedRoute allowedRoles={['admin', 'super_admin']}>
        <div>Admin Panel</div>
      </ProtectedRoute>
    );

    expect(screen.queryByText('Admin Panel')).not.toBeInTheDocument();
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
  });

  it('renders protected content when user has allowed role', () => {
    useAuthModule.useAuth.mockReturnValue({
      loading: false,
      isAuthenticated: true,
      user: { id: 'u_admin', role: 'admin' },
      role: 'admin',
      must_change_password: false,
    });

    renderWithRouter(
      <ProtectedRoute allowedRoles={['admin', 'super_admin']}>
        <div>Admin Secret Panel</div>
      </ProtectedRoute>
    );

    expect(screen.getByText('Admin Secret Panel')).toBeInTheDocument();
  });
});

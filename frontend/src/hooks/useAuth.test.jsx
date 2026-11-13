import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { AuthProvider, useAuth } from './useAuth';
import * as authApi from '../api/auth';
import * as clientModule from '../api/client';

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock auth API
vi.mock('../api/auth', () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));

function TestConsumer() {
  const { user, loading, isAuthenticated, logout } = useAuth();
  if (loading) return <div>Loading...</div>;
  return (
    <div>
      <div data-testid="auth-status">{isAuthenticated ? 'logged-in' : 'logged-out'}</div>
      <div data-testid="user-email">{user?.email || 'no-user'}</div>
      <button onClick={logout}>Log Out</button>
    </div>
  );
}

describe('useAuth & AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('fetches /auth/me exactly once on mount', async () => {
    authApi.getMe.mockResolvedValueOnce({
      data: { id: 'u1', email: 'test@sais.edu', role: 'student' },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    // Initial loading state
    expect(screen.getByText('Loading...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-in');
    });

    expect(screen.getByTestId('user-email')).toHaveTextContent('test@sais.edu');
    expect(authApi.getMe).toHaveBeenCalledTimes(1);
  });

  it('handles 401 on initial session check quietly without redirect loops', async () => {
    const error401 = new Error('Unauthorized');
    error401.response = { status: 401 };
    authApi.getMe.mockRejectedValueOnce(error401);

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out');
    });

    expect(screen.getByTestId('user-email')).toHaveTextContent('no-user');
    // On 401 session check, navigate should NOT be called (user is already on landing/login)
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(authApi.getMe).toHaveBeenCalledTimes(1);
  });

  it('logout calls auth API, clears user and navigates to /login', async () => {
    authApi.getMe.mockResolvedValueOnce({
      data: { id: 'u2', email: 'logout@sais.edu', role: 'student' },
    });
    authApi.logout.mockResolvedValueOnce({});

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-in');
    });

    const logoutBtn = screen.getByText('Log Out');
    await act(async () => {
      logoutBtn.click();
    });

    expect(authApi.logout).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('auth-status')).toHaveTextContent('logged-out');
    expect(mockNavigate).toHaveBeenCalledWith('/login', { replace: true });
  });
});

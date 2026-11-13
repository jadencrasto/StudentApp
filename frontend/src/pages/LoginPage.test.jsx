import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from './LoginPage';
import * as authApi from '../api/auth';
import * as useAuthModule from '../hooks/useAuth';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../api/auth', () => ({
  login: vi.fn(),
  getMe: vi.fn(),
}));

vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('react-hot-toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('LoginPage', () => {
  const mockSetToken = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthModule.useAuth.mockReturnValue({
      setToken: mockSetToken,
      user: null,
    });
  });

  it('renders email, password inputs and sign-in button', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    expect(screen.getByPlaceholderText('you@university.edu')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('••••••••')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('submits credentials and redirects student to dashboard', async () => {
    authApi.login.mockResolvedValueOnce({ data: { message: 'ok' } });
    authApi.getMe.mockResolvedValueOnce({
      data: {
        id: 'u1',
        role: 'student',
        onboarding_completed: true,
        must_change_password: false,
      },
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    const emailInput = screen.getByPlaceholderText('you@university.edu');
    const passwordInput = screen.getByPlaceholderText('••••••••');
    const submitBtn = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'student@sais.edu' } });
    fireEvent.change(passwordInput, { target: { value: 'Pass1234!' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith({
        email: 'student@sais.edu',
        password: 'Pass1234!',
      });
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('redirects admin to /admin on login', async () => {
    authApi.login.mockResolvedValueOnce({ data: { message: 'ok' } });
    authApi.getMe.mockResolvedValueOnce({
      data: {
        id: 'adm1',
        role: 'admin',
        must_change_password: false,
      },
    });

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('you@university.edu'), { target: { value: 'admin@sais.edu' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'AdminPass123!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/admin');
    });
  });

  it('displays error message on invalid credentials', async () => {
    const errorObj = new Error('Bad request');
    errorObj.response = { data: { detail: 'Invalid credentials' } };
    authApi.login.mockRejectedValueOnce(errorObj);

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('you@university.edu'), { target: { value: 'wrong@sais.edu' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'WrongPass!' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });
});

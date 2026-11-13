import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RegisterPage from './RegisterPage';
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
  register: vi.fn(),
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

describe('RegisterPage', () => {
  const mockSetToken = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthModule.useAuth.mockReturnValue({
      setToken: mockSetToken,
      user: null,
    });
  });

  it('renders all registration fields', () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    );

    expect(screen.getByPlaceholderText('john_doe')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('John Doe')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('you@university.edu')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('••••••••')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
  });

  it('shows validation error if password is less than 8 characters', async () => {
    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('john_doe'), { target: { value: 'johndoe' } });
    fireEvent.change(screen.getByPlaceholderText('John Doe'), { target: { value: 'John Doe' } });
    fireEvent.change(screen.getByPlaceholderText('you@university.edu'), { target: { value: 'john@sais.edu' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'short' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByText('Password must be at least 8 characters')).toBeInTheDocument();
    expect(authApi.register).not.toHaveBeenCalled();
  });

  it('submits form with valid data and redirects new student', async () => {
    authApi.register.mockResolvedValueOnce({ data: { message: 'created' } });
    authApi.getMe.mockResolvedValueOnce({
      data: {
        id: 'u_new',
        role: 'student',
        onboarding_completed: false,
      },
    });

    render(
      <MemoryRouter>
        <RegisterPage />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('john_doe'), { target: { value: 'johndoe' } });
    fireEvent.change(screen.getByPlaceholderText('John Doe'), { target: { value: 'John Doe' } });
    fireEvent.change(screen.getByPlaceholderText('you@university.edu'), { target: { value: 'john@sais.edu' } });
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'SecurePass123!' } });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(authApi.register).toHaveBeenCalledWith({
        username: 'johndoe',
        full_name: 'John Doe',
        email: 'john@sais.edu',
        password: 'SecurePass123!',
      });
      expect(mockNavigate).toHaveBeenCalledWith('/onboarding');
    });
  });
});

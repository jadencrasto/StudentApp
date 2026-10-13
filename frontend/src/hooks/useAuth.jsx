import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { getMe } from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async () => {
    const token = localStorage.getItem('sais_token');
    if (!token) {
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const { data } = await getMe();
      setUser(data);
    } catch (error) {
      localStorage.removeItem('sais_token');
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const setToken = useCallback((token) => {
    localStorage.setItem('sais_token', token);
    fetchUser();
  }, [fetchUser]);

  const logout = useCallback(() => {
    localStorage.removeItem('sais_token');
    setUser(null);
    window.location.href = '/login';
  }, []);

  const value = {
    user,
    role: user?.role || 'student',
    onboarding_completed: !!user?.onboarding_completed,
    must_change_password: !!user?.must_change_password,
    institution: user?.institution || null,
    cohort: user?.cohort || null,
    join_request_status: user?.join_request_status || null,
    loading,
    isAuthenticated: !!user,
    setToken,
    logout,
    refreshUser: fetchUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

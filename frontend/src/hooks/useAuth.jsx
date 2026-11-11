import { useState, useEffect, useCallback, createContext, useContext } from 'react';
import { getMe } from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (quiet = false) => {
    const token = localStorage.getItem('sais_token');
    if (!token) {
      setLoading(false);
      return;
    }

    if (!quiet) setLoading(true);
    try {
      const { data } = await getMe();
      setUser(data);
    } catch (error) {
      localStorage.removeItem('sais_token');
      setUser(null);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  // ── Auto-refresh on window focus & tab visibility change ────────────────
  useEffect(() => {
    function handleVisibilityOrFocus() {
      if (document.visibilityState === 'visible' && localStorage.getItem('sais_token')) {
        fetchUser(true);
      }
    }

    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    return () => {
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
    };
  }, [fetchUser]);

  // ── Conditional 45-second poll ONLY while a join request is pending ────
  useEffect(() => {
    if (user?.join_request_status !== 'pending') return;

    const intervalId = setInterval(() => {
      // Pause poll when tab is hidden in background
      if (!document.hidden && localStorage.getItem('sais_token')) {
        fetchUser(true);
      }
    }, 45000);

    return () => clearInterval(intervalId);
  }, [user?.join_request_status, fetchUser]);

  const setToken = useCallback((token) => {
    localStorage.setItem('sais_token', token);
    fetchUser();
  }, [fetchUser]);

  const logout = useCallback(() => {
    localStorage.removeItem('sais_token');
    setUser(null);
    window.location.href = '/login';
  }, []);

  const isClassStudent = Boolean(
    user?.is_active !== false &&
    user?.role === 'student' &&
    user?.institution?.id &&
    user?.cohort?.id
  );

  const isInInstitutionWithoutClass = Boolean(
    user?.is_active !== false &&
    user?.role === 'student' &&
    user?.institution?.id &&
    !user?.cohort?.id
  );

  const isIndependentStudent = Boolean(
    user?.is_active !== false &&
    user?.role === 'student' &&
    !user?.institution?.id
  );

  const value = {
    user,
    role: user?.role || null,
    is_active: user?.is_active !== false,
    onboarding_completed: !!user?.onboarding_completed,
    must_change_password: !!user?.must_change_password,
    institution: user?.institution || null,
    cohort: user?.cohort || null,
    join_request_status: user?.join_request_status || null,
    join_request_type: user?.join_request_type || null,
    join_requested_cohort_name: user?.join_requested_cohort_name || null,
    isClassStudent,
    isInInstitutionWithoutClass,
    isIndependentStudent,
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

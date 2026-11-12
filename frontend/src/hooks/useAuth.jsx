import { useState, useEffect, useCallback, createContext, useContext, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getMe, logout as authLogout } from '../api/auth';
import { setOnUnauthorizedHandler } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Clear legacy localStorage token on first load (Phase 8D: Pure cookie auth)
  useEffect(() => {
    localStorage.removeItem('sais_token');
  }, []);

  const inFlightPromiseRef = useRef(null);
  const hasFetchedOnMountRef = useRef(false);
  const userRef = useRef(user);

  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const fetchUser = useCallback(async (quiet = false) => {
    if (inFlightPromiseRef.current) {
      return inFlightPromiseRef.current;
    }

    if (!quiet) setLoading(true);

    const promise = (async () => {
      try {
        const { data } = await getMe();
        setUser(data);
        return data;
      } catch (error) {
        // 401 on session check quietly sets user to null (logged out)
        setUser(null);
        return null;
      } finally {
        inFlightPromiseRef.current = null;
        if (!quiet) setLoading(false);
      }
    })();

    inFlightPromiseRef.current = promise;
    return promise;
  }, []);

  // Handle 401 on real API calls in protected pages via router navigation (no full reload)
  useEffect(() => {
    const handleUnauthorized = () => {
      setUser(null);
      localStorage.removeItem('sais_token');
      localStorage.removeItem('sais_user');
      navigate('/login', { replace: true });
    };

    setOnUnauthorizedHandler(handleUnauthorized);
    window.addEventListener('auth:unauthorized', handleUnauthorized);

    return () => {
      setOnUnauthorizedHandler(null);
      window.removeEventListener('auth:unauthorized', handleUnauthorized);
    };
  }, [navigate]);

  // Initial session check on startup (runs once, handles React StrictMode double effect)
  useEffect(() => {
    if (hasFetchedOnMountRef.current) return;
    hasFetchedOnMountRef.current = true;
    fetchUser();
  }, [fetchUser]);

  // ── Auto-refresh on window focus & tab visibility change ────────────────
  // Only refresh if currently logged in
  useEffect(() => {
    if (!user) return;

    function handleVisibilityOrFocus() {
      if (document.visibilityState === 'visible' && userRef.current) {
        fetchUser(true);
      }
    }

    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    return () => {
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
    };
  }, [user, fetchUser]);

  // ── Conditional 45-second poll ONLY while a join request is pending ────
  useEffect(() => {
    if (user?.join_request_status !== 'pending') return;

    const intervalId = setInterval(() => {
      // Pause poll when tab is hidden in background
      if (!document.hidden) {
        fetchUser(true);
      }
    }, 45000);

    return () => clearInterval(intervalId);
  }, [user?.join_request_status, fetchUser]);

  const setToken = useCallback((profile) => {
    if (profile && typeof profile === 'object' && profile.id) {
      setUser(profile);
    } else {
      // Cookie is set directly by backend HTTP response; re-fetch user profile
      fetchUser();
    }
  }, [fetchUser]);

  const logout = useCallback(async () => {
    try {
      await authLogout();
    } catch {
      // ignore
    }
    localStorage.removeItem('sais_token');
    localStorage.removeItem('sais_user');
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

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

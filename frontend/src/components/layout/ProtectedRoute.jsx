import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

export default function ProtectedRoute({ children, allowedRoles }) {
  const { user, isAuthenticated, loading, role, must_change_password } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="w-10 h-10 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Forced password change guard: must change password before accessing anything else
  if (must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  // Prevent users who don't need password change from getting stuck on /change-password
  if (!must_change_password && location.pathname === '/change-password') {
    if (role === 'super_admin') return <Navigate to="/super-admin" replace />;
    if (role === 'admin') return <Navigate to="/admin" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  // Role-based access control
  if (allowedRoles && !allowedRoles.includes(role)) {
    if (role === 'super_admin') return <Navigate to="/super-admin" replace />;
    if (role === 'admin') return <Navigate to="/admin" replace />;
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}


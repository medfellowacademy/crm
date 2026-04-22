import React, { useEffect } from 'react';
import { ROLES } from '../config/rbac';
import AdminDashboard from '../features/dashboards/AdminDashboard';
import CounselorDashboard from '../features/dashboards/CounselorDashboard';
import ProfessionalDashboard from '../pages/ProfessionalDashboard';

const RoleBasedDashboard = () => {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userRole = user.role;

  useEffect(() => {
    document.title = `Dashboard - ${user.name || 'User'}`;
  }, [user.name]);

  // Render role-specific dashboard
  switch (userRole) {
    case ROLES.ADMIN:
      return <AdminDashboard />;
    
    case ROLES.COUNSELLOR:
      return <CounselorDashboard user={user} />;
    
    case ROLES.MANAGER:
      // Manager gets admin-like view but with team focus
      return <AdminDashboard />;
    
    case ROLES.FINANCE:
      // Finance gets specialized revenue dashboard
      return <AdminDashboard />; // Can create FinanceDashboard later
    
    default:
      // Fallback to professional dashboard
      return <ProfessionalDashboard />;
  }
};

export default RoleBasedDashboard;

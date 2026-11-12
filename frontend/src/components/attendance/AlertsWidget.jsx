/**
 * src/components/attendance/AlertsWidget.jsx
 * ─────────────────────────────────────────────
 * Standalone widget for the dashboard sidebar showing attendance alerts.
 */
import { useState, useEffect } from 'react';
import { Bell, TrendingUp } from 'lucide-react';
import { getAttendanceAlerts } from '../../api/attendance';
import AlertBanner from './AlertBanner';
import RecoveryPlanModal from './RecoveryPlanModal';

export default function AlertsWidget({ initialAlerts = null }) {
    const [alerts, setAlerts] = useState(initialAlerts || []);
    const [loading, setLoading] = useState(initialAlerts === null);
    const [dismissed, setDismissed] = useState([]);
    const [recoverySubject, setRecoverySubject] = useState(null);

    useEffect(() => {
        if (initialAlerts !== null) {
            setAlerts(initialAlerts);
            setLoading(false);
            return;
        }

        let isMounted = true;
        getAttendanceAlerts()
            .then(({ data }) => {
                if (isMounted) setAlerts(data || []);
            })
            .catch(() => { })
            .finally(() => {
                if (isMounted) setLoading(false);
            });

        return () => {
            isMounted = false;
        };
    }, [initialAlerts]);

    const visible = alerts.filter((a) => !dismissed.includes(a.id));
    const criticalCount = visible.filter((a) => a.severity === 'critical').length;

    return (
        <>
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Bell size={17} className="text-slate-400" />
                        <h3 className="font-display text-base text-white">Attendance Alerts</h3>
                    </div>
                    {criticalCount > 0 && (
                        <span className="px-2 py-0.5 bg-red-400/10 border border-red-400/30 text-red-400 text-xs font-bold rounded-full">
                            {criticalCount} urgent
                        </span>
                    )}
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
                    </div>
                ) : visible.length === 0 ? (
                    <div className="py-8 flex flex-col items-center text-center gap-2">
                        <div className="w-10 h-10 bg-green-400/10 rounded-full flex items-center justify-center">
                            <TrendingUp size={20} className="text-green-400" />
                        </div>
                        <p className="text-sm text-slate-400">All clear — no attendance concerns.</p>
                    </div>
                ) : (
                    <div className="space-y-2.5">
                        {visible.slice(0, 5).map((alert) => (
                            <AlertBanner
                                key={alert.id}
                                alert={alert}
                                onDismiss={(id) => setDismissed((d) => [...d, id])}
                                onViewRecovery={(subjectId) => setRecoverySubject(subjectId)}
                            />
                        ))}
                        {visible.length > 5 && (
                            <p className="text-xs text-slate-500 text-center pt-1">
                                +{visible.length - 5} more alerts
                            </p>
                        )}
                    </div>
                )}
            </div>

            <RecoveryPlanModal
                subjectId={recoverySubject}
                onClose={() => setRecoverySubject(null)}
            />
        </>
    );
}

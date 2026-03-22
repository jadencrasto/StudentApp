import { useEffect, useRef, useState } from 'react';
import { notificationService } from '../services/notificationService';
import { api } from '../lib/api';

export function useClassNotifications() {
  const checkInterval = useRef(null);
  const [todayClasses, setTodayClasses] = useState([]);

  // Fetch today's classes
  const fetchClasses = async () => {
    try {
      const { data } = await api.get('/timetable/today');
      setTodayClasses(data);
    } catch (error) {
      console.error('Failed to fetch today classes for notifications', error);
    }
  };

  useEffect(() => {
    fetchClasses();
    const interval = setInterval(fetchClasses, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // Attempt to request permission if currently default
    if (notificationService.permission === 'default') {
      notificationService.requestPermission();
    }

    if (!todayClasses?.length) return;

    const checkClasses = () => {
      const now = new Date();
      const currentTimeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      
      const timeToMinutes = (timeStr) => {
        const [h, m] = timeStr.split(':').map(Number);
        return h * 60 + m;
      };

      const currentMins = timeToMinutes(currentTimeStr);

      todayClasses.forEach(classItem => {
        // Only notify for active classes
        if (!classItem.is_active) return;

        const startMins = timeToMinutes(classItem.start_time);
        const endMins = timeToMinutes(classItem.end_time);

        // 1. Class Start Notification (up to 1 minute before or exactly at start)
        if (Math.abs(startMins - currentMins) <= 1) {
          // If the attendance isn't marked yet for today
          if (!classItem.attendance_status) {
            const notifiedKey = `notified-start-${classItem.id}-${classItem.day_of_week}`;
            if (!sessionStorage.getItem(notifiedKey)) {
              notificationService.sendClassStartNotification(
                classItem.subject_name,
                classItem.room,
                classItem.start_time
              );
              sessionStorage.setItem(notifiedKey, 'true');
            }
          }
        }

        // 2. Unmarked Class Reminder (Right when class ends)
        if (endMins === currentMins) {
          if (!classItem.attendance_status) {
            const notifiedKey = `notified-end-${classItem.id}-${classItem.day_of_week}`;
            if (!sessionStorage.getItem(notifiedKey)) {
              notificationService.sendUnmarkedClassNotification(
                classItem.subject_name,
                `${classItem.start_time} - ${classItem.end_time}`
              );
              sessionStorage.setItem(notifiedKey, 'true');
            }
          }
        }
      });
    };

    // Check every minute
    checkInterval.current = setInterval(checkClasses, 60000);
    // Check immediately on mount/data load
    checkClasses();

    return () => {
      if (checkInterval.current) {
        clearInterval(checkInterval.current);
      }
    };
  }, [todayClasses]);
}

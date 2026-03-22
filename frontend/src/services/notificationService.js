class NotificationService {
  constructor() {
    this.permission = window.Notification ? window.Notification.permission : 'denied';
  }

  async requestPermission() {
    if (!window.Notification) return false;
    
    try {
      this.permission = await window.Notification.requestPermission();
      return this.permission === 'granted';
    } catch (error) {
      console.error('Error requesting notification permission:', error);
      return false;
    }
  }

  sendClassStartNotification(className, room, startTime) {
    if (this.permission !== 'granted') return;

    try {
      const notification = new window.Notification('Class Starting Now', {
        body: `${className} is starting at ${startTime}${room ? ` in ${room}` : ''}.`,
        icon: '/vite.svg', // Or any appropriate icon
        tag: `class-start-${className}-${startTime}`, // Prevent duplicate notifications
      });

      notification.onclick = function() {
        window.focus();
        this.close();
      };
    } catch (error) {
      console.error('Error sending notification:', error);
    }
  }

  sendUnmarkedClassNotification(className, Time) {
    if (this.permission !== 'granted') return;

    try {
      const notification = new window.Notification('Attendance Unmarked', {
        body: `Your ${className} class (${Time}) ended, but attendance isn't marked. Let's update it!`,
        icon: '/vite.svg',
        tag: `unmarked-class-${className}-${Time}`,
      });

      notification.onclick = function() {
        window.focus();
        // Ideally navigate to attendance page or dashboard
        this.close();
      };
    } catch (error) {
      console.error('Error sending notification:', error);
    }
  }
}

export const notificationService = new NotificationService();

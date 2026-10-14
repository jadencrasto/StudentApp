import client from './client';

export const register = (data) => client.post('/auth/register', data);
export const login = (data) => client.post('/auth/login', data);
export const getMe = () => client.get('/auth/me');
export const changePassword = (data) => client.post('/auth/change-password', data);
export const updateProfile = (data) => client.patch('/me/profile', data);
export const submitJoin = (data) => client.post('/join', data);
export const submitClassJoin = (data) => client.post('/join/class', data);


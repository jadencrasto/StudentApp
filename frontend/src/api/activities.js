import client from './client'
export const getActivities    = ()      => client.get('/activities')
export const createActivity   = (data)  => client.post('/activities', data)
export const deleteActivity   = (id)    => client.delete(`/activities/${id}`)
export const deleteActivityById = (id, deleteSeries = false) =>
  client.delete(`/activities/${id}?delete_series=${deleteSeries}`)
export const updateActivity   = (id, data, updateSeries = false) =>
  client.put(`/activities/${id}?update_series=${updateSeries}`, data)
export const refreshConflicts = ()      => client.post('/activities/refresh-conflicts')

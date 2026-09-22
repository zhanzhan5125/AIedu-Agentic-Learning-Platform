import axios from 'axios'
import router from '@/router'

const apiV1 = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  withCredentials: true
})

apiV1.interceptors.request.use(config => {
  const user = JSON.parse(localStorage.getItem('user') || 'null')
  const token = user && user.token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

apiV1.interceptors.response.use(
  response => response.data,
  async error => {
    const original = error.config || {}
    const currentUser = JSON.parse(localStorage.getItem('user') || 'null')
    if (!currentUser || !currentUser.token) {
      return Promise.reject(error)
    }
    if (error.response && error.response.status === 401 && !original.__retried &&
        !String(original.url).includes('/auth/')) {
      original.__retried = true
      try {
        const refreshed = await apiV1.post('/auth/refresh')
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        if (user && refreshed.data && refreshed.data.token) {
          user.token = refreshed.data.token
          localStorage.setItem('user', JSON.stringify(user))
          original.headers = original.headers || {}
          original.headers.Authorization = `Bearer ${refreshed.data.token}`
          return apiV1(original)
        }
      } catch (_) {
        const latestUser = JSON.parse(localStorage.getItem('user') || 'null')
        if (latestUser) {
          localStorage.removeItem('user')
          router.push('/login').catch(() => {})
        }
      }
    }
    return Promise.reject(error)
  }
)

export default apiV1

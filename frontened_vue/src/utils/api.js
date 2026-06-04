// src/utils/api.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 请求拦截器：每次发请求前自动在 Header 带有 Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理 401 鉴权失败
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      alert("登录已过期或未授权，请重新登录");
      localStorage.removeItem('token');
      localStorage.removeItem('username');
      // 🌟 核心修改：使用原生跳转，不依赖任何 router 实例，彻底规避循环引用
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const getAdminTransactions = (params) => apiClient.get('/admin/transactions', { params });

export const updateTransactionManualCheck = (transactionId, payload) => (
  apiClient.put(`/admin/transactions/${encodeURIComponent(transactionId)}/manual-check`, payload)
);

export const scanPaymentAuth = (payload) => apiClient.post('/payment/scan-auth', payload);

export const getCustomerBlacklist = (params) => apiClient.get('/admin/blacklist', { params });

export const liftCustomerBlacklist = (customerId, payload) => (
  apiClient.put(`/admin/blacklist/${encodeURIComponent(customerId)}/lift`, payload)
);

export const getTransactionVideoUrl = (transactionId, videoUrl = '') => {
  const fallbackUrl = `/api/admin/transactions/${encodeURIComponent(transactionId)}/video`;
  return new URL(videoUrl || fallbackUrl, new URL(apiClient.defaults.baseURL).origin).toString();
};

export const getTransactionVideoStreamUrl = (transactionId) => {
  const streamUrl = `/api/admin/transactions/${encodeURIComponent(transactionId)}/video-stream`;
  return new URL(streamUrl, new URL(apiClient.defaults.baseURL).origin).toString();
};

export default apiClient;

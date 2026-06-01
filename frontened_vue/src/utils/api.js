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

export default apiClient;
// src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    // 智能终端主页（需要登录）
    path: '/',
    name: 'Terminal',
    component: () => import('../views/TerminalView.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 商家运营后台（需要登录）
    path: '/admin',
    name: 'Admin',
    component: () => import('../views/AdminDashboard.vue'),
    meta: { requiresAuth: true }
  },
  {
    // 登录页
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 全局路由守卫（全新标准写法，杜绝废弃警告）
router.beforeEach((to) => {
  const token = localStorage.getItem('token');
  // 严格验证 token 是否有效
  const isAuthenticated = token && token !== 'null' && token !== 'undefined' && token.trim() !== '';

  // 1. 如果去往需要权限的页面（如 / 或 /admin）且没有登录，直接强行重定向到登录页
  if (to.meta.requiresAuth && !isAuthenticated) {
    return '/login';
  }

  // 2. 如果已经登录了，还手欠去访问 /login，直接送回主页
  if (to.path === '/login' && isAuthenticated) {
    return '/';
  }

  // 3. 其他情况（如正常访问登录页或已登录访问主页）直接放行
  return true;
})

export default router
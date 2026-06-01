import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router' // 引入刚刚创建的路由

const app = createApp(App)

// 告诉 Vue 使用路由
app.use(router)

app.mount('#app')
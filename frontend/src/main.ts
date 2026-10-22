import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createQueryClient } from './api/queryClient'
import App from './App.vue'
import { router } from './router'
import './style.css'

createApp(App).use(createPinia()).use(VueQueryPlugin, { queryClient: createQueryClient() }).use(router).mount('#app')

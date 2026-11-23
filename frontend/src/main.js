import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './styles.css'

createApp(App).use(router).mount('#app')

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}))
}

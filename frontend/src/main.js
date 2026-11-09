import { createApp } from 'vue'
import App from './App.vue'
import './fonts.js'
import './style.css'
import { captureToken } from './api.js'

captureToken()

const app = createApp(App)
app.mount('#app')

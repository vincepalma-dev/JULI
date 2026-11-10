import { createApp } from 'vue'
import App from './App.vue'
import './fonts.js'
import './style.css'
import { captureToken } from './api.js'
import { restoreTheme } from './theme.js'

captureToken()
restoreTheme()

const app = createApp(App)
app.mount('#app')

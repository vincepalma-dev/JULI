import { createApp } from 'vue'
import App from './App.vue'
import './fonts.js'
import './style.css'
import { captureToken } from './api.js'
import { restoreMascot } from './mascot.js'
import { restoreTheme } from './theme.js'

captureToken()
restoreTheme()
restoreMascot()

const app = createApp(App)
app.mount('#app')

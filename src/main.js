import App from './App.svelte'
import { mount } from 'svelte'
mount(App, { target: document.getElementById('app') })

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
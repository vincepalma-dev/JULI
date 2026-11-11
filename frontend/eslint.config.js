import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

// Correctness rules only (no style rules): the core recommended set plus the
// Vue essentials.
export default [
  { ignores: ['dist/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/essential'],
  {
    languageOptions: { globals: globals.browser },
    rules: {
      // Composer, Icon and Sidebar can't clash with an HTML element.
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    files: ['*.config.js', 'tests/**', 'e2e/**'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
]

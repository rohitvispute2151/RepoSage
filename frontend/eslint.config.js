import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import vue from 'eslint-plugin-vue'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'src/api/schema.d.ts', 'playwright-report', 'test-results', '.lighthouseci', 'coverage'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    // Untrusted-content policy: raw HTML sinks are banned outright.
    rules: {
      'vue/no-v-html': 'error',
      'no-restricted-properties': [
        'error',
        { property: 'innerHTML', message: 'Untrusted text must never be rendered as HTML.' },
        { property: 'outerHTML', message: 'Untrusted text must never be rendered as HTML.' },
        { property: 'insertAdjacentHTML', message: 'Untrusted text must never be rendered as HTML.' },
      ],
      'no-undef': 'off', // TypeScript already reports undefined names
      'vue/multi-word-component-names': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
    },
  },
  {
    files: ['tests/**/*.ts', 'e2e/**/*.ts'],
    rules: { 'no-restricted-properties': 'off' },
  },
)

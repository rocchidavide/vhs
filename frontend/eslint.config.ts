import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginVitest from '@vitest/eslint-plugin'
import pluginOxlint from 'eslint-plugin-oxlint'
import pluginVueI18n from '@intlify/eslint-plugin-vue-i18n'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,ts,mts,tsx}'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**']),

  ...pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  {
    ...pluginVitest.configs.recommended,
    files: ['src/**/__tests__/*'],
  },

  // Internationalization: no text written directly in the templates (docs/conventions.md).
  // The plugin types its flat config loosely (ecmaVersion: number); the content is valid.
  ...(pluginVueI18n.configs.recommended as unknown as Parameters<typeof defineConfigWithVueTs>),
  {
    name: 'app/i18n-settings',
    settings: {
      'vue-i18n': {
        localeDir: './src/locales/*.json',
        messageSyntaxVersion: '^11.0.0',
      },
    },
  },
  {
    name: 'app/i18n',
    files: ['src/**/*.vue'],
    rules: {
      '@intlify/vue-i18n/no-raw-text': [
        'error',
        {
          // Attributes read by the user or by assistive technologies are checked too.
          attributes: { '/.+/': ['title', 'aria-label', 'placeholder', 'alt'] },
          // Symbols and numbers alone are not language (separators, arrows, units), and an
          // empty alt marks a decorative image.
          ignorePattern: '^[-–—·•×+%/#:()←→↑↓⋮\\s\\d]*$',
        },
      ],
      '@intlify/vue-i18n/no-missing-keys': 'error',
      '@intlify/vue-i18n/no-unused-keys': 'off',
      '@intlify/vue-i18n/no-v-html': 'error',
    },
  },

  ...pluginOxlint.buildFromOxlintConfigFile('.oxlintrc.json'),
)

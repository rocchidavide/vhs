<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import StorageBanner from '@/components/StorageBanner.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const { t } = useI18n()

const links = [
  { to: { name: 'dashboard' }, labelKey: 'nav.home' },
  { to: { name: 'library' }, labelKey: 'nav.library' },
  { to: { name: 'collections' }, labelKey: 'nav.collections' },
  { to: { name: 'tags' }, labelKey: 'nav.tags' },
  { to: { name: 'downloads' }, labelKey: 'nav.downloads' },
]

async function logout() {
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">{{ t('app.name') }}</div>
      <nav>
        <RouterLink v-for="link in links" :key="link.labelKey" :to="link.to" class="nav-link">
          {{ t(link.labelKey) }}
        </RouterLink>
      </nav>
      <div class="account">
        <span>{{ auth.user?.username }}</span>
        <button type="button" class="link-button" @click="logout">{{ t('nav.logout') }}</button>
      </div>
    </aside>
    <main class="content">
      <StorageBanner />
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  min-height: 100vh;
}

.sidebar {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding: 1.5rem 1rem;
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
}

.brand {
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: 0.2em;
  color: var(--color-accent);
}

nav {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.nav-link {
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  color: var(--color-text-muted);
}

.nav-link:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.nav-link.router-link-exact-active {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.account {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
  color: var(--color-text-muted);
}

.content {
  padding: 2rem;
}

@media (max-width: 720px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: none;
    border-bottom: 1px solid var(--color-border);
  }
}
</style>

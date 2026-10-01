import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
        { path: 'library', name: 'library', component: () => import('@/pages/LibraryPage.vue') },
        {
          path: 'collections',
          name: 'collections',
          component: () => import('@/pages/CollectionsPage.vue'),
        },
        {
          path: 'collections/:id(\\d+)',
          name: 'collection',
          component: () => import('@/pages/CollectionPage.vue'),
        },
        { path: 'tags', name: 'tags', component: () => import('@/pages/TagsPage.vue') },
        {
          path: 'downloads',
          name: 'downloads',
          component: () => import('@/pages/DownloadsPage.vue'),
        },
        {
          path: 'videos/:id(\\d+)',
          name: 'video',
          component: () => import('@/pages/VideoPage.vue'),
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.checked) {
    await auth.fetchMe()
  }
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }
})

export default router

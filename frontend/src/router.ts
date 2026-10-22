import { createRouter, createWebHistory } from 'vue-router'

export const routes = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { title: 'Open a task' } },
  { path: '/repos', name: 'repos', component: () => import('@/views/ReposView.vue'), meta: { title: 'Repositories' } },
  { path: '/tasks/new', name: 'new-task', component: () => import('@/views/NewTaskView.vue'), meta: { title: 'New task' } },
  {
    path: '/tasks/:id',
    component: () => import('@/views/TaskLayout.vue'),
    props: true,
    children: [
      { path: '', name: 'trajectory', component: () => import('@/views/TrajectoryView.vue'), meta: { title: 'Trajectory' } },
      { path: 'review', name: 'review', component: () => import('@/views/ReviewView.vue'), meta: { title: 'Patch review' } },
      { path: 'answer', name: 'answer', component: () => import('@/views/AnswerView.vue'), meta: { title: 'Answer' } },
    ],
  },
  { path: '/evals/compare', name: 'eval-compare', component: () => import('@/views/EvalCompareView.vue'), meta: { title: 'Eval compare' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue'), meta: { title: 'Not found' } },
]

export const router = createRouter({ history: createWebHistory(), routes })

router.afterEach((to) => {
  document.title = `${String(to.meta.title ?? 'RepoSage')} · RepoSage Console`
})

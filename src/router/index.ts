import { createRouter, createWebHistory } from 'vue-router';
import EntryPage from '../views/EntryPage.vue';
import LobbyPage from '../views/LobbyPage.vue';
import GameRoom from '../views/GameRoom.vue';
import AdminPage from '../views/AdminPage.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'Entry',
      component: EntryPage
    },
    {
      path: '/lobby',
      name: 'Lobby',
      component: LobbyPage
    },
    {
      path: '/game',
      name: 'Game',
      component: GameRoom
    },
    {
      // 管理后台：服务端会对 /admin 做本机校验，前端再做一次访问探测
      path: '/admin',
      name: 'Admin',
      component: AdminPage
    }
  ]
});

export default router;

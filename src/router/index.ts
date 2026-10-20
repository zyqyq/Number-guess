import { createRouter, createWebHistory } from 'vue-router';
import EntryPage from '../views/EntryPage.vue';
import LobbyPage from '../views/LobbyPage.vue';
import GameRoom from '../views/GameRoom.vue';

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
    }
  ]
});

export default router;

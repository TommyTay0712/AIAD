<script setup lang="ts">
import SideNav from '../components/layout/SideNav.vue'
import TopBar from '../components/layout/TopBar.vue'
</script>

<template>
  <div class="shell">
    <SideNav />
    <div class="main-panel">
      <TopBar />
      <main class="page-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
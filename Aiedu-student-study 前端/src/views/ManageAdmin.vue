<template>
  <div class="layout-container">
    <!-- Header 部分 -->
    <HeaderComponent />

    <!-- Sidebar 和主内容部分 -->
    <div class="main-container">
      <!-- 侧边栏 -->
      <AsideComponent />

      <!-- 主内容区域 -->
      <el-main>

        <router-view/>

      </el-main>
    </div>
  </div>
</template>

<script>
import HeaderComponent from '../components/Header.vue';
import AsideComponent from '../components/adminHomeAside.vue';

export default {
  components: {
    HeaderComponent,
    AsideComponent,
  },
  data() {
    return {
    };
  },
};
</script>

<style>
.layout-container {
  display: flex;
  flex-direction: column;
  height: 100vh; /* 设置高度为视口的100%，使布局占满整个屏幕 */
}

.main-container {
  display: flex;
  flex: 1; /* 主内容区域占据剩余的空间 */
}


main {
  flex: 1;
  padding: 20px;
}

</style>

import Vue from 'vue'
import App from './App.vue'
import router from './router'
import ElementUI from 'element-ui'
import 'element-ui/lib/theme-chalk/index.css'
import './assets/gloable.css'
import store from './store'
import apiV1 from "@/utils/apiV1"
import axios from 'axios'
import VueAxios from 'vue-axios'
import MessageUnreadBadge from '@/components/MessageUnreadBadge.vue'

Vue.config.productionTip = false

Vue.use(ElementUI, { size: "mini" });
Vue.component('MessageUnreadBadge', MessageUnreadBadge)

Vue.prototype.request=apiV1
Vue.use(VueAxios, apiV1)

const savedUser = JSON.parse(localStorage.getItem('user') || 'null')
if (savedUser && savedUser._backend !== 'fastapi') {
  store.commit('clearUser')
  store.commit('clearCourse')
  store.commit('clearCurrentAssignment')
  store.commit('clearStudent')
}

// 导航守卫
router.beforeEach((to, from, next) => {
  // 在这里进行全局操作，比如判断localStorage是否有用户信息
  const user = localStorage.getItem("user") ? JSON.parse(localStorage.getItem("user")) : null

  if (!user && to.path !== '/login') {
    // 如果没有用户信息且不是访问登录页面，则跳转到登录页面
    next('/login');
    // 在这里进行全局错误处理，例如显示一个错误提示
    Vue.prototype.$notify.error({
      title: '错误',
      message: '用户未登录'
    });
  } else if (user && to.meta.roles && !to.meta.roles.includes(user.role === 'manager' ? 'admin' : user.role)) {
    Vue.prototype.$notify.error({ title: '无权访问', message: '当前角色不能打开该页面' });
    next(false);
  } else {
    // 如果有用户信息或者访问登录页面，则继续导航
    next();
  }
});

new Vue({
  router,
  store,
  render: h => h(App)
}).$mount('#app')

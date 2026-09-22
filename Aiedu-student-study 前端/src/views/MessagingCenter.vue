<template>
  <div class="message-shell">
    <aside><div class="aside-title"><b>{{ centerTitle }}</b><el-badge :value="unread" /></div>
      <div v-if="isCourseScope" class="locked-course"><i class="el-icon-reading" /> {{ currentCourseTitle }}</div>
      <el-select v-else v-model="selectedOffering" clearable placeholder="全部课程" @change="loadThreads"><el-option v-for="c in courses" :key="c.id" :label="c.title" :value="c.id" /></el-select>
      <el-button v-if="selectedOffering" class="new-button" plain type="primary" size="small" @click="openDirectDialog">发起课程私聊</el-button>
      <el-button v-if="isTeacher && selectedOffering" class="new-button" type="primary" size="small" @click="announcementVisible=true">发布课程公告</el-button>
      <div v-for="item in notifications" :key="`n-${item.id}`" class="thread" :class="{active:active&&active.notificationId===item.id}" @click="openNotification(item)"><b>{{ item.title }}</b><p>{{ item.body }}</p><el-badge v-if="!item.is_read" value="新" /></div>
      <div v-for="item in threads" :key="item.id" class="thread" :class="{active:active&&active.id===item.id}" @click="openThread(item)"><b>{{ item.title || kindText(item.kind) }}</b><small v-if="!isCourseScope">{{ courseTitle(item.offering_id) }}</small><p>{{ item.last_message || '暂无消息' }}</p><el-badge v-if="item.unread_count" :value="item.unread_count" /></div>
    </aside>
    <main><template v-if="active"><header><h3>{{ active.title || kindText(active.kind) }}</h3></header>
      <section class="messages"><div v-for="m in messages" :key="m.id" class="bubble" :class="{mine:m.sender_id===currentUserId}"><small>{{ m.sender_name }}</small><p>{{ m.body }}</p></div></section>
      <footer v-if="active.kind==='direct'||(isTeacher&&active.kind==='announcement')"><el-input v-model="draft" @keyup.enter.native="send" placeholder="输入消息"/><el-button type="primary" @click="send">发送</el-button></footer>
    </template><el-empty v-else description="选择一条会话查看消息" /></main>
    <el-dialog title="发布课程公告" :visible.sync="announcementVisible" width="460px"><el-input v-model="announcement.title" placeholder="公告标题"/><el-input v-model="announcement.body" type="textarea" :rows="5" placeholder="公告内容" class="announcement-body"/><span slot="footer"><el-button @click="announcementVisible=false">取消</el-button><el-button type="primary" @click="publish">教师确认并发布</el-button></span></el-dialog>
    <el-dialog title="发起课程私聊" :visible.sync="directVisible" width="460px">
      <el-empty v-if="!contacts.length" description="当前教学班暂无可联系成员" />
      <el-radio-group v-else v-model="selectedContact" class="contact-list">
        <el-radio v-for="contact in contacts" :key="contact.id" :label="contact.id">
          {{ contact.name }}（{{ roleText(contact.role) }} · {{ contact.account }}）
        </el-radio>
      </el-radio-group>
      <span slot="footer"><el-button @click="directVisible=false">取消</el-button><el-button type="primary" :disabled="!selectedContact" @click="createDirect">开始私聊</el-button></span>
    </el-dialog>
  </div>
</template>
<script>
import apiV1 from '@/utils/apiV1'
export default{
  data(){return{courses:[],selectedOffering:null,threads:[],notifications:[],active:null,messages:[],draft:'',unread:0,announcementVisible:false,announcement:{title:'',body:''},directVisible:false,contacts:[],selectedContact:null,realtimeSocket:null,reconnectTimer:null,pollTimer:null,isDestroyed:false}},
  computed:{
    user(){return this.$store.getters.getUser||{}},
    currentUserId(){return this.user.id},
    isTeacher(){return(this.user.role||this.user.identity)==='teacher'},
    isCourseScope(){return this.$route.meta.messageScope==='course'},
    centerTitle(){return this.isCourseScope?'本课程消息':'全部课程消息'},
    currentCourseTitle(){const course=this.$store.getters.getCourse||{};return course.title||course.tittle||'当前课程'}
  },
  async created(){
    await this.loadCourses()
    if(this.isCourseScope){
      const course=this.$store.getters.getCourse||{}
      this.selectedOffering=course.id||course.offeringId||course.courseCode||null
      if(!this.selectedOffering){
        this.$message.warning('未选择课程，请从课程页面进入消息中心')
        this.$router.push({name:'学生主页'})
        return
      }
    }
    await this.loadThreads()
    this.connectRealtime()
    this.pollTimer=setInterval(()=>this.loadThreads(true),30000)
  },
  beforeDestroy(){this.isDestroyed=true;if(this.pollTimer)clearInterval(this.pollTimer);if(this.reconnectTimer)clearTimeout(this.reconnectTimer);if(this.realtimeSocket)this.realtimeSocket.close()},
  methods:{
    async loadCourses(){try{const path=this.isTeacher?'/teacher/offerings':'/student/courses';this.courses=(await apiV1.get(path)).data.records||[]}catch(_){this.courses=[]}},
    async loadThreads(silent=false){
      try{
        const query=this.selectedOffering?`?offering_id=${this.selectedOffering}`:''
        const res=await apiV1.get(`/messages/threads${query}`)
        this.threads=res.data.records||[]
        const noticeQuery=this.selectedOffering?`?page_size=100&offering_id=${this.selectedOffering}`:'?page_size=100'
        this.notifications=(await apiV1.get(`/notifications${noticeQuery}`)).data.records||[]
        this.unread=(res.data.unread_count||0)+this.notifications.filter(i=>!i.is_read).length
        window.dispatchEvent(new CustomEvent('message-unread-changed'))
        if(this.active&&!this.threads.some(item=>item.id===this.active.id)&&!this.active.notificationId){this.active=null;this.messages=[]}
      }catch(error){if(!silent){this.threads=[];this.notifications=[];this.$message.error(this.errorMessage(error,'消息加载失败'))}}
    },
    async openNotification(item){try{this.active={notificationId:item.id,title:item.title,kind:'system'};this.messages=[{id:`notice-${item.id}`,sender_id:null,sender_name:'系统',body:item.body,created_at:item.created_at}];if(!item.is_read)await apiV1.put(`/notifications/${item.id}/read`);await this.loadThreads(true)}catch(error){this.$message.error(this.errorMessage(error,'通知读取失败'))}},
    async openThread(item){try{this.active=item;this.messages=(await apiV1.get(`/messages/threads/${item.id}`)).data.records||[];await apiV1.put(`/messages/threads/${item.id}/read`);await this.loadThreads(true)}catch(error){this.$message.error(this.errorMessage(error,'会话加载失败'))}},
    async send(){if(!this.draft.trim()||!this.active||!this.active.id)return;const body=this.draft.trim();try{await apiV1.post(`/messages/threads/${this.active.id}`,{body});this.draft='';await this.openThread(this.active)}catch(error){this.$message.error(this.errorMessage(error,'消息发送失败'))}},
    async publish(){if(!this.announcement.title||!this.announcement.body)return this.$message.warning('请填写完整公告');try{const res=await apiV1.post(`/messages/offerings/${this.selectedOffering}/announcements`,this.announcement);this.announcementVisible=false;this.announcement={title:'',body:''};await this.loadThreads();const item=this.threads.find(i=>i.id===res.data.thread_id);if(item)await this.openThread(item)}catch(error){this.$message.error(this.errorMessage(error,'公告发布失败'))}},
    async openDirectDialog(){
      try{this.contacts=(await apiV1.get(`/messages/offerings/${this.selectedOffering}/contacts`)).data||[];this.selectedContact=null;this.directVisible=true}
      catch(error){this.$message.error(this.errorMessage(error,'联系人加载失败'))}
    },
    async createDirect(){
      if(!this.selectedContact)return
      try{const res=await apiV1.post('/messages/direct-threads',{offering_id:this.selectedOffering,recipient_id:this.selectedContact});this.directVisible=false;await this.loadThreads();const item=this.threads.find(thread=>thread.id===res.data.id);if(item)await this.openThread(item)}
      catch(error){this.$message.error(this.errorMessage(error,'私聊创建失败'))}
    },
    connectRealtime(){
      const token=this.user.token
      if(!token||this.isDestroyed)return
      const protocol=window.location.protocol==='https:'?'wss:':'ws:'
      const configured=process.env.VUE_APP_FASTAPI_WS_URL
      const endpoint=configured||(process.env.NODE_ENV==='development'
        ?`${protocol}//${window.location.hostname}:9091/api/v1/ws/messages`
        :`${protocol}//${window.location.host}/api/v1/ws/messages`)
      const socket=new WebSocket(`${endpoint}?token=${encodeURIComponent(token)}`)
      this.realtimeSocket=socket
      socket.onmessage=async event=>{
        let payload={}
        try{payload=JSON.parse(event.data)}catch(_){return}
        if(payload.thread_id&&this.active&&this.active.id===payload.thread_id)await this.openThread(this.active)
        else await this.loadThreads(true)
      }
      socket.onclose=()=>{if(!this.isDestroyed){this.reconnectTimer=setTimeout(()=>this.connectRealtime(),3000)}}
      socket.onerror=()=>socket.close()
    },
    courseTitle(id){const course=this.courses.find(item=>item.id===id);return course?course.title:`课程 ${id}`},
    kindText(kind){return({direct:'私聊',announcement:'课程公告',system:'系统通知',agent_status:'智能体任务'})[kind]||kind},
    roleText(role){return({teacher:'教师',student:'学生',manager:'管理员'})[role]||role},
    errorMessage(error,fallback){
      if(!error||!error.response)return '消息服务未连接，请确认 FastAPI（9091端口）已经启动'
      return error.response.data?.msg||`${fallback}（HTTP ${error.response.status}）`
    }
  }
}
</script>
<style scoped>
.message-shell{display:grid;grid-template-columns:320px 1fr;height:calc(100vh - 70px);background:#f6f8fb}aside{background:white;border-right:1px solid #e7ebef;padding:20px;overflow:auto}.aside-title{display:flex;justify-content:space-between;margin-bottom:16px}.locked-course{padding:10px 12px;background:#f0f6ff;color:#2379d8;border-radius:6px;margin-bottom:12px}.new-button{width:100%;margin:6px 0}.thread{position:relative;padding:14px;margin-top:8px;border-radius:8px;cursor:pointer}.thread:hover,.thread.active{background:#edf5ff}.thread small{display:block;color:#409eff;margin-top:5px}.thread p{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#7b8794;margin:6px 0 0}.thread .el-badge{position:absolute;right:10px;top:10px}main{display:flex;flex-direction:column;padding:24px 36px}.messages{flex:1;overflow:auto}.bubble{max-width:65%;margin:14px 0}.bubble.mine{margin-left:auto;text-align:right}.bubble p{display:inline-block;background:white;padding:12px 16px;border-radius:12px;margin:4px 0}.bubble.mine p{background:#2379d8;color:white}footer{display:flex;gap:10px}.announcement-body{margin-top:12px}.contact-list{display:flex;flex-direction:column;gap:16px}.contact-list .el-radio{margin-right:0}
</style>

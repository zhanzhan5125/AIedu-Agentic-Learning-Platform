<template>
  <section class="ai-chat-page">
    <div class="chat-shell">
      <header class="chat-header">
        <div class="assistant-identity">
          <div class="brand-orb">杏</div>
          <div>
            <div class="assistant-name">问答杏台 <span class="online-dot"></span></div>
            <div class="assistant-subtitle">课程专属 AI 学习助手</div>
          </div>
        </div>
        <div class="header-actions">
          <div class="course-chip" :title="courseTitle">
            <i class="el-icon-reading"></i><span>{{ courseTitle }}</span>
          </div>
        </div>
      </header>

      <div class="chat-workspace">
        <div class="chat-main">
          <main ref="messageContainer" class="conversation-area">
        <div v-if="messages.length === 0" class="welcome-panel">
          <div class="welcome-logo">杏</div>
          <h1>今天想学习什么？</h1>
          <p>我会结合 <strong>{{ courseTitle }}</strong> 的课程内容，帮你解释知识点、梳理思路和生成练习。</p>
          <div class="suggestion-grid">
            <button v-for="item in suggestions" :key="item.title" type="button"
                    class="suggestion-card" @click="useSuggestion(item.prompt)">
              <span class="suggestion-icon"><i :class="item.icon"></i></span>
              <span class="suggestion-copy">
                <b>{{ item.title }}</b><small>{{ item.description }}</small>
              </span>
              <i class="el-icon-right suggestion-arrow"></i>
            </button>
          </div>
        </div>

        <div v-else class="message-list">
          <article v-for="message in messages" :key="message.id"
                   class="message-row" :class="`message-${message.role}`">
            <div v-if="message.role === 'assistant'" class="message-avatar assistant-avatar">杏</div>
            <div class="message-body">
              <div v-if="message.role === 'assistant'" class="message-author">问答杏台</div>
              <div class="message-bubble">
                <span v-if="!message.loading">{{ message.content }}</span>
                <span v-else class="thinking-state">
                  <span>正在思考</span><i></i><i></i><i></i>
                </span>
              </div>
              <el-tag v-if="message.policyMode === 'guided'" class="policy-tag" size="mini" type="warning">作业辅导模式 · 不提供直接答案</el-tag>
              <div v-if="message.citations && message.citations.length" class="citation-list">
                <span v-for="citation in message.citations" :key="`${citation.resource_id}-${citation.position}`">资料：{{ citation.title }}</span>
              </div>
            </div>
            <div v-if="message.role === 'user'" class="message-avatar user-avatar">{{ userInitial }}</div>
          </article>
        </div>
          </main>

          <footer class="composer-area">
        <div class="composer-wrap">
          <textarea ref="textarea" v-model="text" class="chat-input" rows="1" maxlength="4000"
                    placeholder="向杏台提问课程知识……" @input="adjustTextareaHeight"
                    @keydown.enter.exact.prevent="send"></textarea>
          <div class="composer-bottom">
            <span class="input-hint">Enter 发送 · Shift + Enter 换行</span>
            <button type="button" class="send-button" :class="{ ready: canSend }"
                    :disabled="!canSend" aria-label="发送问题" @click="send">
              <i :class="isSending ? 'el-icon-loading' : 'el-icon-top'"></i>
            </button>
          </div>
        </div>
        <p class="answer-notice">AI 回答可能存在偏差，请结合课程资料与教师讲解进行判断。</p>
          </footer>
        </div>

        <aside class="conversation-sidebar">
          <button type="button" class="sidebar-new-button" :disabled="conversationLoading"
                  @click="createConversation">
            <i class="el-icon-plus"></i><span>新对话</span>
          </button>
          <div class="history-heading">
            <span>历史对话</span><span class="history-count">{{ conversations.length }}</span>
          </div>
          <div v-if="!conversationEnabled" class="history-tip">
            <i class="el-icon-lock"></i>
            <span>重新登录后即可同步对话记录</span>
          </div>
          <div v-else-if="conversationLoading && conversations.length === 0" class="history-tip">
            <i class="el-icon-loading"></i><span>正在加载对话</span>
          </div>
          <div v-else-if="conversations.length === 0" class="history-tip">
            <i class="el-icon-chat-dot-round"></i><span>还没有历史对话</span>
          </div>
          <div v-else class="history-list">
            <button v-for="item in conversations" :key="item.id" type="button"
                    class="history-item" :class="{ active: item.id === activeConversationId }"
                    @click="selectConversation(item)">
              <span class="history-icon"><i class="el-icon-chat-line-round"></i></span>
              <span class="history-content">
                <b>{{ item.title }}</b><small>{{ formatConversationTime(item) }}</small>
              </span>
              <span class="history-delete" title="删除对话" @click.stop="archiveConversation(item)">
                <i class="el-icon-delete"></i>
              </span>
            </button>
          </div>
        </aside>
      </div>
    </div>
  </section>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  name: 'AIChat',
  data() {
    return {
      user: null,
      course: null,
      text: '',
      messages: [],
      isSending: false,
      messageSequence: 0,
      conversations: [],
      activeConversationId: null,
      conversationOfferingId: null,
      conversationLoading: false,
      conversationEnabled: false,
      conversationSelectionToken: 0,
      suggestions: [
        { title: '梳理核心知识', description: '总结重点并建立知识框架',
          prompt: '请帮我梳理这门课程当前章节的核心知识点，并说明它们之间的关系。', icon: 'el-icon-collection' },
        { title: '解释一个概念', description: '用通俗例子辅助理解',
          prompt: '请选择这门课程中一个重要但容易混淆的概念，用简单例子为我讲解。', icon: 'el-icon-chat-line-round' },
        { title: '生成练习题', description: '通过练习检查掌握情况',
          prompt: '请根据这门课程的内容生成三道由易到难的练习题，先不要给出答案。', icon: 'el-icon-edit-outline' },
        { title: '制定复习计划', description: '把学习任务拆成小步骤',
          prompt: '请帮我为这门课程制定一份简洁的阶段复习计划。', icon: 'el-icon-date' }
      ]
    }
  },
  computed: {
    courseTitle() {
      if (!this.course) return '当前课程'
      return this.course.title || this.course.tittle || this.course.cno || '当前课程'
    },
    userInitial() {
      return this.user && this.user.name ? this.user.name.slice(0, 1) : '我'
    },
    canSend() {
      return Boolean(this.text.trim()) && !this.isSending
    }
  },
  created() {
    this.user = this.$store.getters.getUser
    this.course = this.$store.getters.getCourse
    this.conversationEnabled = Boolean(this.user && this.user.token)
    this.initializeConversations()
  },
  methods: {
    nextMessageId() {
      this.messageSequence += 1
      return `${Date.now()}-${this.messageSequence}`
    },
    useSuggestion(prompt) {
      this.text = prompt
      this.$nextTick(() => {
        this.adjustTextareaHeight()
        this.$refs.textarea.focus()
      })
    },
    adjustTextareaHeight() {
      const textarea = this.$refs.textarea
      if (!textarea) return
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
    },
    async send() {
      const question = this.text.trim()
      if (!question || this.isSending) return

      this.isSending = true
      try {
        await this.ensureConversation()
      } catch (error) {
        this.isSending = false
        this.$message.error(this.requestErrorMessage(error))
        return
      }

      this.messages.push({ id: this.nextMessageId(), role: 'user', content: question, loading: false })
      const assistantMessage = { id: this.nextMessageId(), role: 'assistant', content: '', loading: true }
      this.messages.push(assistantMessage)
      this.text = ''
      this.$nextTick(() => {
        this.adjustTextareaHeight()
        this.scrollToBottom()
      })

      let serverPersisted = false
      const conversationId = this.activeConversationId
      try {
        const response = await apiV1.post(`/conversations/${conversationId}/ask`, {
            idempotency_key: `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`,
            content: question,
            hint_level: 0
        })
        const result = response && response.data ? response.data : response
        this.$set(assistantMessage, 'content', result.answer || '问题已经处理完成。')
        this.$set(assistantMessage, 'citations', result.citations || [])
        this.$set(assistantMessage, 'policyMode', result.policy_mode)
        serverPersisted = true
      } catch (error) {
        const recovered = conversationId
          ? await this.recoverPersistedExchange(conversationId, question)
          : false
        if (recovered) serverPersisted = true
        else this.$set(assistantMessage, 'content', this.requestErrorMessage(error))
      } finally {
        assistantMessage.loading = false
        if (serverPersisted) await this.loadConversations()
        this.isSending = false
        this.$nextTick(() => this.scrollToBottom())
      }
    },
    async waitForJob(jobId) {
      for (let attempt = 0; attempt < 60; attempt++) {
        const response = await apiV1.get(`/jobs/${jobId}`)
        if (response.data.status === 'succeeded') {
          const result = response.data.result || {}
          return result.content || result.message || '问题已经处理完成。'
        }
        if (response.data.status === 'failed') throw new Error(response.data.error || 'AI 任务失败')
        await new Promise(resolve => setTimeout(resolve, 1000))
      }
      throw new Error('AI 任务超时')
    },
    async initializeConversations() {
      if (!this.conversationEnabled) return
      this.conversationLoading = true
      try {
        this.conversationOfferingId = await this.resolveFastapiOfferingId()
        await this.loadConversations()
        if (this.conversations.length > 0) await this.selectConversation(this.conversations[0])
      } catch (error) {
        this.conversationEnabled = false
      } finally {
        this.conversationLoading = false
      }
    },
    async resolveFastapiOfferingId() {
      return this.course.id || this.course.offeringId || this.course.courseCode
    },
    async loadConversations() {
      const response = await apiV1.get('/conversations', {
        params: { offering_id: this.conversationOfferingId }
      })
      this.conversations = response.data.records
    },
    async createConversation() {
      if (!this.conversationEnabled || this.conversationLoading) {
        if (!this.conversationEnabled) this.$message.warning('请重新登录后使用历史对话功能')
        return
      }
      this.conversationLoading = true
      try {
        const response = await apiV1.post('/conversations', {
          offering_id: this.conversationOfferingId,
          title: '新对话'
        })
        this.conversations.unshift(response.data)
        this.conversationSelectionToken += 1
        this.activeConversationId = response.data.id
        this.messages = []
        this.text = ''
        this.$nextTick(() => this.$refs.textarea && this.$refs.textarea.focus())
      } finally {
        this.conversationLoading = false
      }
    },
    async ensureConversation() {
      if (!this.conversationEnabled || this.activeConversationId) return
      await this.createConversation()
    },
    async selectConversation(item) {
      if (this.isSending || item.id === this.activeConversationId) return
      const selectionToken = ++this.conversationSelectionToken
      this.activeConversationId = item.id
      this.messages = []
      this.conversationLoading = true
      try {
        const response = await apiV1.get(`/conversations/${item.id}/messages`)
        if (selectionToken !== this.conversationSelectionToken) return
        this.messages = this.storedMessages(response.data.records)
        this.$nextTick(() => this.scrollToBottom())
      } finally {
        if (selectionToken === this.conversationSelectionToken) this.conversationLoading = false
      }
    },
    storedMessages(records) {
      return (records || []).map(message => ({
        id: `stored-${message.id}`,
        role: message.role,
        content: message.content || '',
        citations: message.citations || [],
        policyMode: message.policy_mode,
        loading: false
      }))
    },
    async recoverPersistedExchange(conversationId, question) {
      try {
        const response = await apiV1.get(`/conversations/${conversationId}/messages`)
        const records = response.data.records || []
        let userIndex = -1
        for (let index = records.length - 1; index >= 0; index -= 1) {
          if (records[index].role === 'user' && records[index].content === question) {
            userIndex = index
            break
          }
        }
        const recovered = userIndex >= 0 && records.slice(userIndex + 1).some(
          message => message.role === 'assistant' && message.status === 'completed'
        )
        if (!recovered || this.activeConversationId !== conversationId) return false
        this.messages = this.storedMessages(records)
        return true
      } catch (_) {
        return false
      }
    },
    async persistMessage(role, content, status = 'completed') {
      if (!this.conversationEnabled || !this.activeConversationId || !content) return
      try {
        const response = await apiV1.post(`/conversations/${this.activeConversationId}/messages`, {
          role, content, status
        })
        const current = this.conversations.find(item => item.id === this.activeConversationId)
        if (current) {
          current.title = response.data.title
          current.last_message_at = new Date().toISOString()
        }
      } catch (error) {
        this.$message.warning('回答已显示，但本次对话记录同步失败')
      }
    },
    async archiveConversation(item) {
      if (this.isSending) return
      await apiV1.delete(`/conversations/${item.id}`)
      this.conversations = this.conversations.filter(row => row.id !== item.id)
      if (this.activeConversationId === item.id) {
        this.conversationSelectionToken += 1
        this.activeConversationId = null
        this.messages = []
        if (this.conversations.length > 0) await this.selectConversation(this.conversations[0])
      }
    },
    formatConversationTime(item) {
      const value = item.last_message_at || item.updated_at || item.created_at
      if (!value) return '刚刚'
      const date = new Date(value)
      const today = new Date()
      if (date.toDateString() === today.toDateString()) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
      }
      return `${date.getMonth() + 1}月${date.getDate()}日`
    },
    requestErrorMessage(error) {
      if (!error || !error.response) return '网络连接异常，请稍后再试。'
      return error.response.data?.msg || error.response.data?.detail || '智能问答服务暂时不可用，请稍后再试。'
    },
    scrollToBottom() {
      const container = this.$refs.messageContainer
      if (container) container.scrollTop = container.scrollHeight
    }
  }
}
</script>

<style scoped>
.ai-chat-page {
  --blue: #1d6fe8;
  height: calc(100vh - 104px);
  min-height: 590px;
  color: #172033;
  background: radial-gradient(circle at 12% 8%, rgba(61,139,253,.12), transparent 31%),
              linear-gradient(180deg, #f7faff 0%, #eef5ff 100%);
  border: 1px solid #dce9fb;
  border-radius: 18px;
  overflow: hidden;
}
.chat-shell { height: 100%; display: flex; flex-direction: column; background: rgba(255,255,255,.72); }
.chat-header {
  height: 74px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
  padding: 0 28px; background: rgba(255,255,255,.95); border-bottom: 1px solid #e5edf8;
  box-shadow: 0 4px 18px rgba(39,91,157,.05); z-index: 2;
}
.assistant-identity, .header-actions { display: flex; align-items: center; }
.brand-orb, .message-avatar, .welcome-logo {
  display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700;
  background: linear-gradient(145deg, #3b91ff, #1558c9); box-shadow: 0 7px 16px rgba(29,111,232,.25);
}
.brand-orb { width: 42px; height: 42px; margin-right: 12px; border-radius: 13px; font-size: 18px; }
.assistant-name { display: flex; align-items: center; gap: 8px; font-size: 17px; font-weight: 700; }
.online-dot { width: 7px; height: 7px; border-radius: 50%; background: #31c58d; box-shadow: 0 0 0 3px #e0f8ef; }
.assistant-subtitle { margin-top: 4px; color: #8490a4; font-size: 12px; }
.header-actions { gap: 12px; }
.course-chip {
  max-width: 250px; display: flex; align-items: center; gap: 7px; padding: 8px 12px;
  color: #45617f; background: #f3f7fc; border: 1px solid #e2eaf4; border-radius: 10px; font-size: 13px;
}
.course-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-workspace { flex: 1; min-height: 0; display: flex; }
.chat-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.conversation-sidebar {
  width: 250px; flex: 0 0 250px; display: flex; flex-direction: column; padding: 18px 14px;
  box-sizing: border-box; background: rgba(248,251,255,.96); border-left: 1px solid #dfe9f5;
}
.sidebar-new-button {
  width: 100%; height: 42px; display: flex; align-items: center; justify-content: center; gap: 8px;
  color: #fff; background: linear-gradient(135deg,#3288f5,#1764d8); border: 0; border-radius: 11px;
  box-shadow: 0 7px 17px rgba(29,111,232,.2); cursor: pointer; font-size: 14px; transition: .2s ease;
}
.sidebar-new-button:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 10px 20px rgba(29,111,232,.27); }
.sidebar-new-button:disabled { opacity: .65; cursor: wait; }
.history-heading { display: flex; align-items: center; justify-content: space-between; margin: 22px 5px 10px; color: #6f7f94; font-size: 12px; font-weight: 600; }
.history-count { min-width: 20px; padding: 2px 5px; box-sizing: border-box; color: #718198; background: #e9f0f8; border-radius: 8px; text-align: center; }
.history-list { flex: 1; min-height: 0; overflow-y: auto; padding-right: 2px; }
.history-item {
  width: 100%; display: flex; align-items: center; padding: 10px 8px; margin-bottom: 5px; color: #3d4d62;
  text-align: left; background: transparent; border: 1px solid transparent; border-radius: 11px; cursor: pointer;
}
.history-item:hover { background: #eef5ff; }
.history-item.active { color: #175fcb; background: #e5f1ff; border-color: #c9e0fb; }
.history-icon { width: 30px; height: 30px; flex: 0 0 30px; display: grid; place-items: center; color: #5c7da5; background: #edf3fa; border-radius: 9px; }
.history-item.active .history-icon { color: #fff; background: var(--blue); }
.history-content { min-width: 0; display: flex; flex: 1; flex-direction: column; gap: 4px; margin-left: 9px; }
.history-content b { overflow: hidden; font-size: 13px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.history-content small { color: #9aa6b6; font-size: 10px; }
.history-delete { padding: 6px; color: transparent; border-radius: 7px; }
.history-item:hover .history-delete, .history-item.active .history-delete { color: #9aa8ba; }
.history-delete:hover { color: #e35b68 !important; background: #fff; }
.history-tip { display: flex; flex-direction: column; align-items: center; gap: 9px; padding: 30px 12px; color: #9aa7b7; text-align: center; font-size: 12px; line-height: 1.6; }
.history-tip i { font-size: 20px; color: #78a9e7; }
.conversation-area { flex: 1; min-height: 0; overflow-y: auto; scroll-behavior: smooth; }
.welcome-panel {
  width: min(820px, calc(100% - 48px)); min-height: 100%; margin: 0 auto; padding: 34px 0 28px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; box-sizing: border-box;
}
.welcome-logo {
  width: 68px; height: 68px; border: 6px solid rgba(222,237,255,.95); border-radius: 22px;
  box-shadow: 0 15px 35px rgba(24,102,211,.24); font-size: 27px;
}
.welcome-panel h1 { margin: 22px 0 10px; font-size: 30px; line-height: 1.25; letter-spacing: -.5px; }
.welcome-panel > p { max-width: 600px; margin: 0; color: #728097; text-align: center; font-size: 14px; line-height: 1.8; }
.welcome-panel > p strong { color: var(--blue); font-weight: 600; }
.suggestion-grid { width: 100%; display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; margin-top: 30px; }
.policy-tag { margin-top: 8px; }
.citation-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; color: #6b7785; font-size: 12px; }
.citation-list span { background: #f0f5fa; border-radius: 4px; padding: 4px 7px; }
.suggestion-card {
  min-height: 76px; display: flex; align-items: center; padding: 14px 16px; text-align: left; color: #26364b;
  background: rgba(255,255,255,.92); border: 1px solid #dfe9f6; border-radius: 14px;
  box-shadow: 0 7px 20px rgba(51,91,138,.06); cursor: pointer; transition: .22s ease;
}
.suggestion-card:hover { border-color: #9fc7f8; box-shadow: 0 12px 26px rgba(29,111,232,.12); transform: translateY(-2px); }
.suggestion-icon { width: 38px; height: 38px; flex-shrink: 0; display: grid; place-items: center; color: var(--blue); background: #eaf3ff; border-radius: 11px; font-size: 17px; }
.suggestion-copy { min-width: 0; display: flex; flex: 1; flex-direction: column; gap: 5px; margin-left: 12px; }
.suggestion-copy b { font-size: 14px; }
.suggestion-copy small { overflow: hidden; color: #8a96a8; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.suggestion-arrow { margin-left: 8px; color: #a8b5c7; }
.message-list { width: min(860px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 24px; }
.message-row { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 26px; }
.message-user { justify-content: flex-end; padding-left: 14%; }
.message-assistant { padding-right: 10%; }
.message-avatar { width: 36px; height: 36px; flex: 0 0 36px; border-radius: 11px; font-size: 14px; }
.user-avatar { color: #35628f; background: #e3eefb; box-shadow: none; }
.message-body { min-width: 0; }
.message-user .message-body { display: flex; justify-content: flex-end; }
.message-author { margin: 0 0 7px 2px; color: #516077; font-size: 12px; font-weight: 600; }
.message-bubble { padding: 13px 16px; border-radius: 15px; font-size: 14px; line-height: 1.75; overflow-wrap: anywhere; white-space: pre-wrap; }
.message-assistant .message-bubble { color: #26364b; background: #fff; border: 1px solid #e0e9f5; border-top-left-radius: 5px; box-shadow: 0 7px 22px rgba(51,91,138,.07); }
.message-user .message-bubble { color: #fff; background: linear-gradient(135deg,#2f84f3,#1764d8); border-top-right-radius: 5px; box-shadow: 0 8px 20px rgba(29,111,232,.19); }
.thinking-state { display: inline-flex; align-items: center; gap: 5px; color: #718096; }
.thinking-state i { width: 5px; height: 5px; border-radius: 50%; background: #2f80ed; animation: thinking 1.15s infinite ease-in-out; }
.thinking-state i:nth-child(3) { animation-delay: .14s; } .thinking-state i:nth-child(4) { animation-delay: .28s; }
@keyframes thinking { 0%,70%,100% { opacity:.35; transform:translateY(0); } 35% { opacity:1; transform:translateY(-3px); } }
.composer-area { flex-shrink: 0; padding: 12px 24px 14px; background: linear-gradient(180deg,rgba(247,250,255,0),#f8fbff 24%); }
.composer-wrap {
  width: min(860px,100%); margin: 0 auto; padding: 11px 12px 9px 16px; box-sizing: border-box;
  background: #fff; border: 1px solid #cddff5; border-radius: 17px; box-shadow: 0 10px 30px rgba(32,90,157,.13); transition: .2s ease;
}
.composer-wrap:focus-within { border-color: #78b1f6; box-shadow: 0 12px 32px rgba(29,111,232,.17),0 0 0 3px rgba(47,128,237,.08); }
.chat-input { width: 100%; min-height: 28px; max-height: 160px; display: block; padding: 3px 0; color: #26364b; background: transparent; border: 0; outline: 0; resize: none; overflow-y: auto; box-sizing: border-box; font: inherit; font-size: 14px; line-height: 1.6; }
.chat-input::placeholder { color: #9ca9ba; }
.composer-bottom { display: flex; align-items: center; justify-content: space-between; margin-top: 5px; }
.input-hint { color: #a0aabb; font-size: 11px; }
.send-button { width: 34px; height: 34px; display: grid; place-items: center; color: #a7b3c3; background: #edf1f6; border: 0; border-radius: 10px; cursor: not-allowed; transition: .2s ease; }
.send-button.ready { color: #fff; background: linear-gradient(145deg,#3b91ff,#1764d8); box-shadow: 0 6px 14px rgba(29,111,232,.24); cursor: pointer; }
.send-button.ready:hover { transform: translateY(-1px); box-shadow: 0 8px 17px rgba(29,111,232,.3); }
.answer-notice { margin: 7px 0 0; color: #9ba6b5; text-align: center; font-size: 10px; }
.conversation-area::-webkit-scrollbar, .chat-input::-webkit-scrollbar { width: 6px; }
.conversation-area::-webkit-scrollbar-thumb, .chat-input::-webkit-scrollbar-thumb { background: #cbd9e9; border-radius: 10px; }
@media (max-width: 900px) {
  .ai-chat-page { height: calc(100vh - 94px); min-height: 540px; border-radius: 12px; }
  .chat-header { padding: 0 18px; } .course-chip { display: none; }
  .welcome-panel, .message-list { width: calc(100% - 30px); }
  .suggestion-grid { grid-template-columns: 1fr; }
  .message-user, .message-assistant { padding-left: 0; padding-right: 0; }
  .composer-area { padding: 10px 14px 12px; }
  .conversation-sidebar { width: 210px; flex-basis: 210px; padding: 14px 10px; }
}
@media (max-width: 560px) {
  .assistant-subtitle, .input-hint { display: none; }
  .welcome-panel h1 { font-size: 25px; }
  .conversation-sidebar { width: 178px; flex-basis: 178px; }
}
</style>

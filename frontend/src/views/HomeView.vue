<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage, ElUpload, ElButton, ElIcon, ElPopconfirm } from 'element-plus'
import type { UploadFile } from 'element-plus'
import { Upload, Message as MessageIcon, Plus, Delete } from '@element-plus/icons-vue'
import { marked } from 'marked'
import axios from 'axios'
import { useRouter } from 'vue-router'
import QuestionCards from '../components/QuestionCards.vue'
import type { IntakeAnswer, IntakeQuestion } from '../components/QuestionCards.vue'

interface Message {
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  provisional?: boolean
}

interface Conversation {
  id: string
  title: string
  lastMessage: string
  lastActive: Date
  messages: Message[]
}

interface User {
  id: number
  username: string
}

interface ConversationResponse {
  id: string
  title: string
  last_message: string
  last_active: string
}

const router = useRouter()
const messages = ref<Message[]>([])
const inputMessage = ref('')
const userId = ref('')  // 使用登录用户的真实ID，不再随机生成
const threadId = ref('')

const messagesContainerRef = ref<HTMLElement | null>(null)
const user = ref<User | null>(null)
const isUploading = ref(false)  // 文档上传状态
const uploadProgress = ref(0)  // 上传进度
const sidebarOpen = ref(false)
const isSending = ref(false)
const pendingQuestions = ref<IntakeQuestion[]>([])
const streamStatus = ref('')

// 会话列表
const conversations = ref<Conversation[]>([])
const currentConversation = ref<string>('')

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

// 检查登录状态
const checkLoginStatus = () => {
  const userStr = localStorage.getItem('user')
  if (userStr) {
    const savedUser = JSON.parse(userStr) as User
    user.value = savedUser
    // 使用登录用户的真实ID作为长记忆的user_id
    userId.value = 'user_' + savedUser.id
  } else {
    router.push('/login')
  }
}

// 加载会话列表
const loadConversations = async () => {
  try {
    const token = localStorage.getItem('token')
    const response = await axios.get<{ conversations: ConversationResponse[] }>(`${backendUrl}/conversations/list`, {
      params: {
        user_id: user.value?.id
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.status === 200) {
      conversations.value = response.data.conversations.map((conv) => ({
        id: conv.id,
        title: conv.title,
        lastMessage: conv.last_message,
        lastActive: new Date(conv.last_active),
        messages: []
      }))
      
      // 如果有会话，加载第一个会话
      const firstConversation = conversations.value[0]
      if (firstConversation) {
        await selectConversation(firstConversation.id)
      } else {
        await createNewConversation()
      }
    }
  } catch (error) {
    console.error('加载会话列表失败:', error)
    // 如果加载失败，创建一个新会话
    await createNewConversation()
  }
}

// 创建新会话
const createNewConversation = async () => {
  try {
    // 检查用户是否已登录
    if (!user.value || !user.value.id) {
      ElMessage.error('用户未登录，请重新登录')
      router.push('/login')
      return
    }
    
    const newId = 'conv_' + Math.random().toString(36).substr(2, 9)
    const token = localStorage.getItem('token')
    
    // 调用后端API创建会话
    const response = await axios.post(`${backendUrl}/conversations/create`, {
      id: newId,
      title: newId
    }, {
      params: {
        user_id: user.value.id
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.status === 200) {
      const newConv = response.data.conversation
      const conversation: Conversation = {
        id: newConv.id,
        title: newConv.title,
        lastMessage: newConv.last_message,
        lastActive: new Date(newConv.last_active),
        messages: [{
          role: 'assistant',
          content: '您好！我是智能医疗助手，请问有什么可以帮您？',
          timestamp: new Date()
        }]
      }
      
      conversations.value.unshift(conversation)
      await selectConversation(newId)
      
      // AI欢迎消息由前端展示，后端自动处理持久化
      // 无需前端调用 save_message 接口
    }
  } catch (error) {
    console.error('创建会话失败:', error)
    ElMessage.error('创建会话失败，请重试')
  }
}

// 选择会话
const selectConversation = async (convId: string) => {
  try {
    sidebarOpen.value = false
    currentConversation.value = convId
    const token = localStorage.getItem('token')
    
    // 调用后端API获取会话详情和消息
    const response = await axios.get(`${backendUrl}/conversations/get`, {
      params: {
        conversation_id: convId
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.status === 200) {
      console.log('获取会话详情响应:', response.data)
      const messagesData: Array<{ role: Message['role']; content: string; timestamp?: string }> = response.data.messages || []
      console.log('消息数据:', messagesData)
      
      messages.value = messagesData.map((msg) => ({
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
      }))
      pendingQuestions.value = response.data.intake_questions || []
      
      console.log('处理后的消息:', messages.value)
      
      // 如果消息列表为空，添加AI的欢迎消息
      if (messages.value.length === 0) {
        const welcomeMessage = '您好！我是智能医疗助手，请问有什么可以帮您？'
        messages.value.push({
          role: 'assistant',
          content: welcomeMessage,
          timestamp: new Date()
        })
      }
      
      threadId.value = convId
      scrollToBottom()
    }
  } catch (error) {
    console.error('获取会话详情失败:', error)
    ElMessage.error('获取会话详情失败，请重试')
  }
}

// 删除会话
const deleteConversation = async (convId: string) => {
  try {
    const token = localStorage.getItem('token')
    
    // 调用后端API删除会话
    const response = await axios.delete(`${backendUrl}/conversations/delete`, {
      params: {
        conversation_id: convId
      },
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.status === 200) {
      const index = conversations.value.findIndex(conv => conv.id === convId)
      if (index !== -1) {
        conversations.value.splice(index, 1)
        
        // 如果删除的是当前会话，选择第一个会话或创建新会话
        if (currentConversation.value === convId) {
          const firstConversation = conversations.value[0]
          if (firstConversation) {
            await selectConversation(firstConversation.id)
          } else {
            await createNewConversation()
          }
        }
      }
    }
  } catch (error) {
    console.error('删除会话失败:', error)
    ElMessage.error('删除会话失败，请重试')
  }
}

// 登出
const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  user.value = null
  router.push('/login')
  ElMessage.success('已登出')
}

// 预处理 Markdown 内容：
// 避免将中文/数值区间（如 2~4cm, 3~4次）的单波浪号误识别为 Markdown 删除线（<del>）
// 同时保留真正行内代码块、多行代码块以及真正的删除线 ~~text~~
const preprocessMarkdown = (text: string): string => {
  return text.replace(/(```[\s\S]*?```|`[^`\n]+`)|(?<!~)~(?!~)/g, (match, code) => {
    if (code) return code
    return '～'
  })
}

// 转换Markdown为HTML
const renderContent = (content: string) => {
  if (!content) return ''

  // Markdown may contain patient-entered text or provisional model output.
  // Escape raw HTML before parsing so v-html cannot execute embedded markup.
  const safeContent = preprocessMarkdown(content)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  const markedOptions = {
    breaks: true, // 支持换行
    gfm: true, // 支持GitHub风格的Markdown
    tables: true, // 支持表格
    headerIds: false,
    mangle: false
  }

  const template = document.createElement('template')
  template.innerHTML = marked.parse(safeContent, markedOptions) as string
  template.content.querySelectorAll('a, img').forEach((element) => {
    const attribute = element.tagName === 'A' ? 'href' : 'src'
    const value = element.getAttribute(attribute) || ''
    if (!/^https?:\/\//i.test(value)) element.removeAttribute(attribute)
    if (element.tagName === 'A') element.setAttribute('rel', 'noopener noreferrer')
  })
  return template.innerHTML
}

const splitMessageContent = (content: string) => {
  const match = /(?:^|\n)引用来源[：:]\s*(?:\n|$)/.exec(content)
  if (!match || match.index === undefined) return { body: content, sources: '' }
  return {
    body: content.slice(0, match.index).trim(),
    sources: content.slice(match.index + match[0].length).trim()
  }
}

const messageBody = (content: string) => splitMessageContent(content).body
const messageSources = (content: string) => splitMessageContent(content).sources
const sourceCount = (content: string) => {
  const sources = messageSources(content)
  return sources ? (sources.match(/^\s*-\s+/gm)?.length || 1) : 0
}

// 滚动到最新消息
const scrollToBottom = () => {
  setTimeout(() => {
    if (messagesContainerRef.value) {
      messagesContainerRef.value.scrollTop = messagesContainerRef.value.scrollHeight
    }
  }, 50)
}

const streamChat = async (userMessage: string, cardAnswers?: Record<string, IntakeAnswer>) => {
  if (isSending.value) return false
  const activeThread = threadId.value
  const isCurrent = () => threadId.value === activeThread
  const previousQuestions = [...pendingQuestions.value]
  isSending.value = true
  streamStatus.value = '正在处理…'
  // Card answers are immediately represented by the outgoing user bubble.
  // Remove the duplicate card panel optimistically; restore it if the request fails.
  if (cardAnswers) pendingQuestions.value = []
  messages.value.push({ role: 'user', content: userMessage, timestamp: new Date() })
  messages.value.push({ role: 'assistant', content: '', timestamp: new Date() })
  const assistantIndex = messages.value.length - 1
  scrollToBottom()
  let finished = false

  try {
    const token = localStorage.getItem('token')
    const response = await fetch(`${backendUrl}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ user_id: userId.value, message: userMessage,
        thread_id: activeThread, card_answers: cardAnswers || null })
    })
    if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    const receive = (packet: string) => {
      const event = packet.match(/^event: (.+)$/m)?.[1]
      const dataLine = packet.match(/^data: (.+)$/m)?.[1]
      if (!event || !dataLine) return
      const data = JSON.parse(dataLine)
      if (!isCurrent()) {
        if (event === 'final') finished = true
        return
      }
      const target = messages.value[assistantIndex]
      if (event === 'status') {
        streamStatus.value = ({ intake: '正在整理症状…', processing: '正在处理…',
          questions: '请回答下面的问题', retrieving: '正在查找资料…',
          verifying: '正在核对引用…' } as Record<string, string>)[data.stage] || '正在处理…'
      } else if (event === 'delta' && target) {
        target.content += data.text
        target.provisional = true
        scrollToBottom()
      } else if (event === 'final' && target) {
        target.content = data.message || '暂时没有可显示的回答，请重试。'
        target.provisional = false
        target.timestamp = new Date()
        pendingQuestions.value = data.intake_questions || []
        finished = true
        scrollToBottom()
      } else if (event === 'error') {
        throw new Error(data.message || '回答失败')
      }
    }
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let end = buffer.indexOf('\n\n')
      while (end !== -1) {
        receive(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        end = buffer.indexOf('\n\n')
      }
    }
    if (!finished) throw new Error('流式响应未完成')
  } catch (error) {
    console.error('发送消息失败:', error)
    if (isCurrent()) {
      pendingQuestions.value = previousQuestions
      const target = messages.value[assistantIndex]
      if (target) {
        target.content = '本次回答未完成，请重试。'
        target.provisional = false
      }
      ElMessage.error('发送消息失败，请重试')
    }
  } finally {
    streamStatus.value = ''
    isSending.value = false
    await nextTick()
    if (isCurrent()) scrollToBottom()
  }
  return finished
}

const handleSend = async () => {
  if (!inputMessage.value.trim() || isSending.value || pendingQuestions.value.length) return
  const userMessage = inputMessage.value.trim()
  inputMessage.value = ''
  if (checkPreferenceCommand(userMessage)) {
    messages.value.push({ role: 'user', content: userMessage, timestamp: new Date() })
    messages.value.push({ role: 'assistant', content: '偏好设置已保存', timestamp: new Date() })
    return
  }
  const completed = await streamChat(userMessage)
  if (!completed && !inputMessage.value) inputMessage.value = userMessage
}

const submitCards = async (answers: Record<string, IntakeAnswer>) => {
  const preview = pendingQuestions.value.map((question) => {
    const answer = answers[question.id]
    const labels = (answer?.choices || []).map((value) => value === 'other' ? answer?.other_text || '' :
      question.options.find((option) => option.value === value)?.label || value)
    return `- ${question.title}：${labels.join('、')}`
  }).join('\n')
  await streamChat(preview, answers)
}

const handleKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}



// 通过聊天方式设置偏好
const handleSetPreference = async (key: string, value: string) => {
  try {
    const token = localStorage.getItem('token')
    const response = await axios.post(`${backendUrl}/preferences/save`, {
      key: key,
      value: value
    }, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    if (response.status === 200) {
      ElMessage.success('偏好设置成功')
    }
  } catch (error) {
    console.error('设置偏好失败:', error)
    ElMessage.error('设置偏好失败，请重试')
  }
}

// 检查消息是否包含偏好设置指令
const checkPreferenceCommand = (message: string) => {
  const preferenceRegex = /设置偏好：(\w+)=([^\n]+)/
  const match = message.match(preferenceRegex)
  const key = match?.[1]
  const value = match?.[2]
  if (key && value) {
    handleSetPreference(key.trim(), value.trim())
    return true
  }
  return false
}

// 处理文件上传
const handleFileUpload = async (file: UploadFile) => {
  let progressInterval: ReturnType<typeof setInterval> | undefined
  try {
    // 询问用户文档类型
    const documentType = prompt('请选择文档类型:', '病历本')
    if (!documentType) return
    
    // 显示上传中状态
    isUploading.value = true
    uploadProgress.value = 0
    
    // 模拟进度条动画
    progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += Math.random() * 15
      }
    }, 500)
    
    if (!file.raw) throw new Error('上传文件内容缺失')
    const formData = new FormData()
    formData.append('file', file.raw)
    formData.append('document_type', documentType)
    formData.append('user_id', userId.value)

    const token = localStorage.getItem('token')
    const response = await axios.post(`${backendUrl}/documents/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        'Authorization': `Bearer ${token}`
      }
    })
    
    if (progressInterval !== undefined) clearInterval(progressInterval)
    uploadProgress.value = 100

    if (response.status === 200) {
      // 自动发送消息给 AI，让 AI 读取并回复
      const fileName = file.name || file.raw?.name || '医疗文档'
      const completed = await streamChat(`我上传了一份医疗文档：${fileName}（类型：${documentType}），请分析并提取其中的关键信息。`)
      
      // 完成后关闭上传状态
      setTimeout(() => {
        isUploading.value = false
        uploadProgress.value = 0
      }, 500)
      if (completed) ElMessage.success('文档上传并分析完成！')
    }
  } catch (error) {
    console.error('上传文件失败:', error)
    if (progressInterval !== undefined) clearInterval(progressInterval)
    isUploading.value = false
    uploadProgress.value = 0
    ElMessage.error('上传文件失败，请重试')
  }
  return false // 阻止自动上传
}

onMounted(() => {
  checkLoginStatus()
  // 加载会话列表
  loadConversations()
  scrollToBottom()
})
</script>

<template>
  <div class="langchain-style">
    <div class="main-content">
      <button
        v-if="sidebarOpen"
        class="sidebar-scrim"
        type="button"
        aria-label="关闭会话列表"
        @click="sidebarOpen = false"
      ></button>
      <!-- 左侧会话列表 -->
      <aside class="sidebar" :class="{ 'sidebar-open': sidebarOpen }" aria-label="会话列表">
        <div class="sidebar-brand">
          <span class="logo-mark" aria-hidden="true">✚</span>
          <span class="logo-text">智能医疗助手</span>
        </div>
        <div class="sidebar-header">
          <h3>会话</h3>
          <el-button 
            class="new-conversation-btn"
            size="small"
            @click="createNewConversation"
          >
            <el-icon><Plus /></el-icon>
            新会话
          </el-button>
        </div>
        <div class="conversations-list">
          <div
            v-for="conversation in conversations"
            :key="conversation.id"
            class="conversation-item"
            :class="{ active: currentConversation === conversation.id }"
          >
            <button
              class="conversation-select"
              type="button"
              :aria-current="currentConversation === conversation.id ? 'true' : undefined"
              @click="selectConversation(conversation.id)"
            >
              <span class="conversation-title">{{ conversation.title }}</span>
              <span class="conversation-last-message">{{ conversation.lastMessage }}</span>
              <span class="conversation-time">{{ conversation.lastActive.toLocaleTimeString() }}</span>
            </button>
            <el-popconfirm
              title="确定删除此会话吗？"
              @confirm="deleteConversation(conversation.id)"
            >
              <template #reference>
                <el-button 
                  class="delete-conversation-btn"
                  size="small"
                  :aria-label="`删除会话：${conversation.title}`"
                >
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
        <div class="sidebar-footer">
          <nav class="sidebar-nav" aria-label="主要导航">
            <router-link to="/" class="sidebar-nav-link">首页</router-link>
            <router-link to="/preferences" class="sidebar-nav-link">偏好设置</router-link>
          </nav>
          <div v-if="user" class="sidebar-account">
            <span class="sidebar-user-id">{{ user.username }}</span>
            <button class="sidebar-logout" type="button" @click="handleLogout">登出</button>
          </div>
        </div>
      </aside>

      <!-- 右侧聊天区域 -->
      <main class="chat-area">
        <button
          class="sidebar-toggle chat-sidebar-toggle"
          type="button"
          :aria-expanded="sidebarOpen"
          :aria-label="sidebarOpen ? '关闭会话列表' : '打开会话列表'"
          @click="sidebarOpen = !sidebarOpen"
        >
          <span></span><span></span><span></span>
        </button>
        <div class="messages-container" ref="messagesContainerRef">
          <div class="messages-inner">
            <div
              v-for="(msg, index) in messages"
              :key="`msg-${index}-${msg.timestamp.getTime()}`"
              class="message"
              :class="`message-${msg.role}`"
            >
              <div class="message-content">
                <div v-if="!msg.content" class="message-pending" role="status" aria-label="正在思考">
                  <span class="pending-dots" aria-hidden="true"><i></i><i></i><i></i></span>
                  <span class="pending-label">{{ streamStatus || '正在处理…' }}</span>
                </div>
                <div v-else class="message-text" v-html="renderContent(messageBody(msg.content))"></div>
                <details v-if="msg.role === 'assistant' && messageSources(msg.content)" class="source-disclosure">
                  <summary>
                    <span>参考来源</span>
                    <span class="source-count">{{ sourceCount(msg.content) }} 条</span>
                  </summary>
                  <div class="source-content message-text" v-html="renderContent(messageSources(msg.content))"></div>
                </details>
                <p v-if="msg.provisional" class="message-provisional">生成中 · 内容与引用尚待核对</p>
                <p v-if="msg.content && isSending && index === messages.length - 1 && streamStatus" class="message-stream-status" role="status">{{ streamStatus }}</p>
                <div v-if="msg.content" class="message-time">
                  {{ msg.timestamp.toLocaleTimeString() }}
                </div>
              </div>
            </div>
            <QuestionCards v-if="pendingQuestions.length" :questions="pendingQuestions"
              :busy="isSending" @submit="submitCards" />
          </div>
        </div>

        <div class="input-section">
          <div class="input-container">
            <el-input
              v-model="inputMessage"
              type="textarea"
              :rows="1"
              aria-label="输入医疗问题"
              :placeholder="pendingQuestions.length ? '请先完成上方问诊卡片' : '输入您的医疗问题…'"
              :disabled="pendingQuestions.length > 0"
              @keydown="handleKeyDown"
              resize="none"
            />
            <div class="composer-toolbar">
              <el-upload
                class="upload-demo"
                action=""
                :auto-upload="false"
                :on-change="handleFileUpload"
                :show-file-list="false"
                accept=".pdf"
              >
                <el-button class="langchain-button secondary" :disabled="isUploading">
                  <el-icon><Upload /></el-icon>
                  上传医疗文档
                </el-button>
              </el-upload>
              <el-button
                class="langchain-button primary"
                :disabled="!inputMessage.trim() || isSending || pendingQuestions.length > 0"
                :loading="isSending"
                @click="handleSend"
              >
                <el-icon><MessageIcon /></el-icon>
                发送
              </el-button>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <!-- 文档上传提示框 -->
  <transition name="upload-fade">
    <div v-if="isUploading" class="upload-overlay">
      <div class="upload-dialog">
        <div class="upload-icon">
          <el-icon class="is-loading" :size="48"><Upload /></el-icon>
        </div>
        <div class="upload-text">
          <h3>正在上传并分析文档...</h3>
          <p>请稍候，系统正在提取医疗信息</p>
        </div>
        <div class="upload-progress">
          <el-progress :percentage="uploadProgress" :stroke-width="8" :show-text="false" />
        </div>
      </div>
    </div>
  </transition>
</template>


<style scoped>
/* Hallmark · macrostructure: Workbench · tone: calm clinical · anchor hue: blue
 * pre-emit critique: P4 H4 E4 S5 R5 V4 · contrast: pass
 */
:global(html:has(.langchain-style)),
:global(body:has(.langchain-style)) {
  overflow-x: clip;
}

:global(body:has(.langchain-style)) {
  overflow-y: hidden;
  background: var(--medical-canvas);
}

.langchain-style {
  --el-color-primary: var(--medical-accent);
  width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  display: block;
  overflow: hidden;
  background: var(--medical-canvas);
  color: var(--medical-ink);
  font-family: var(--medical-font-body);
}

.logo-mark {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  flex: none;
  border-radius: var(--medical-radius-sm);
  background: var(--medical-accent);
  color: var(--medical-accent-ink);
  font-size: 20px;
  line-height: 1;
}

.logo-text {
  overflow: hidden;
  color: var(--medical-ink);
  background: none;
  -webkit-text-fill-color: currentColor;
  font-family: var(--medical-font-display);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-brand {
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: var(--medical-space-sm);
  padding: 0 var(--medical-space-md);
  border-bottom: 1px solid var(--medical-line);
}

.main-content {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  max-width: none;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  width: auto;
  height: 100%;
  min-height: 0;
  border: 0;
  border-right: 1px solid var(--medical-line);
  border-radius: 0;
  background: var(--medical-sidebar);
  backdrop-filter: none;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
  padding: 0 var(--medical-space-md);
  border-bottom: 1px solid var(--medical-line);
}

.sidebar-header h3 {
  color: var(--medical-ink);
  font-family: var(--medical-font-display);
  font-size: 14px;
}

.new-conversation-btn {
  min-height: 34px;
  padding: 0 9px;
  border: 1px solid var(--medical-line-strong);
  border-radius: var(--medical-radius-sm);
  background: var(--medical-surface);
  color: var(--medical-accent);
  font-size: 12px;
  transition: background-color var(--medical-duration-short) var(--medical-ease-out);
  white-space: nowrap;
}

.new-conversation-btn:hover {
  border-color: var(--medical-accent);
  background: var(--medical-surface-blue);
  color: var(--medical-accent-hover);
}

.conversations-list {
  flex: 1;
  min-height: 0;
  max-height: none;
  padding: var(--medical-space-sm);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 2px;
  min-height: 82px;
  margin: 0 0 4px;
  padding: 3px;
  border: 1px solid transparent;
  border-radius: var(--medical-radius-md);
  background: transparent;
  transition: background-color var(--medical-duration-short) var(--medical-ease-out);
}

.conversation-item:hover {
  border-color: transparent;
  background: var(--medical-surface-blue);
}

.conversation-item.active {
  border-color: var(--medical-line);
  background: var(--medical-surface);
}

.conversation-select {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  padding: 8px 9px;
  border-radius: var(--medical-radius-sm);
  background: transparent;
  text-align: left;
}

.conversation-title,
.conversation-last-message,
.conversation-time {
  display: block;
  width: 100%;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-title {
  color: var(--medical-ink);
  font-size: 13px;
  font-weight: 600;
}

.conversation-last-message {
  color: var(--medical-ink-soft);
  font-size: 12px;
}

.conversation-time {
  color: var(--medical-muted);
  font-size: 11px;
}

.delete-conversation-btn {
  align-self: flex-start;
  width: 30px;
  min-width: 30px;
  height: 30px;
  margin: 4px 3px 0 0;
  padding: 0;
  border: 0;
  border-radius: var(--medical-radius-sm);
  background: transparent;
  color: var(--medical-muted);
  transition: color var(--medical-duration-short) var(--medical-ease-out),
    background-color var(--medical-duration-short) var(--medical-ease-out);
}

.conversation-item:hover .delete-conversation-btn,
.conversation-item:focus-within .delete-conversation-btn {
  opacity: 1;
  visibility: visible;
}

.delete-conversation-btn:hover {
  background: var(--medical-surface);
  color: var(--medical-danger);
}

.sidebar-footer {
  flex: none;
  padding: 7px;
  border-top: 1px solid var(--medical-line);
  background: var(--medical-sidebar);
}

.sidebar-nav {
  display: grid;
  gap: 2px;
}

.sidebar-nav-link,
.sidebar-logout {
  min-height: 38px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  border: 0;
  border-radius: var(--medical-radius-sm);
  background: transparent;
  color: var(--medical-ink-soft);
  font-size: 13px;
  text-align: left;
  transition: background-color var(--medical-duration-short) var(--medical-ease-out),
    color var(--medical-duration-short) var(--medical-ease-out);
}

.sidebar-nav-link:hover,
.sidebar-nav-link.router-link-exact-active,
.sidebar-logout:hover {
  background: var(--medical-surface-blue);
  color: var(--medical-ink);
}

.sidebar-nav-link.router-link-exact-active {
  color: var(--medical-accent);
  font-weight: 600;
}

.sidebar-account {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 5px;
  padding: 5px 5px 0;
  border-top: 1px solid var(--medical-line);
}

.sidebar-user-id {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--medical-ink-soft);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-logout {
  min-height: 32px;
  flex: none;
  padding: 0 8px;
}

.chat-area {
  position: relative;
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 0;
  overflow: hidden;
  background: var(--medical-surface);
}

.messages-container {
  min-width: 0;
  min-height: 0;
  max-height: none;
  display: block;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: var(--medical-surface);
  backdrop-filter: none;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

.messages-inner {
  width: min(100%, 980px);
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 22px;
  margin: 0 auto;
  padding: 32px clamp(20px, 4vw, 52px) 18px;
}

.message-provisional,
.message-stream-status {
  margin: 8px 0 0;
  color: var(--medical-ink-soft);
  font-size: 12px;
  line-height: 1.5;
}

.message {
  max-width: min(100%, 900px);
  margin: 0;
  padding: 0;
  border-radius: 0;
  animation: none;
  box-shadow: none;
}

.message-assistant {
  align-self: flex-start;
  border: 0;
  background: transparent;
}

.message-user {
  max-width: min(78%, 680px);
  align-self: flex-end;
  padding: 8px 14px 6px;
  border: 1px solid var(--medical-line-strong);
  border-bottom-right-radius: 4px;
  background: var(--medical-user-bubble);
}

.message-user .message-content {
  gap: 2px;
}

.message-user .message-text {
  line-height: 1.45;
}

.message-user .message-time {
  font-size: 10px;
  line-height: 1.2;
  margin-top: 1px;
}

.message-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-text {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--medical-ink);
  font-family: var(--medical-font-body);
  font-size: 14px;
  line-height: 1.72;
}

.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4),
.message-text :deep(h5),
.message-text :deep(h6),
.message-text :deep(strong) {
  color: var(--medical-ink);
}

.message-text :deep(h1),
.message-text :deep(h2),
.message-text :deep(h3),
.message-text :deep(h4),
.message-text :deep(h5),
.message-text :deep(h6) {
  margin: 0.6em 0 0.3em;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.message-text :deep(h1) { font-size: 1.35em; }
.message-text :deep(h2) { font-size: 1.2em; }
.message-text :deep(h3) { font-size: 1.1em; }

.message-text :deep(blockquote) {
  margin: 0.6em 0;
  padding-left: 1em;
  border-left: 2px solid var(--medical-line-strong);
  border-left-color: var(--medical-line-strong);
  color: var(--medical-ink-soft);
}

.message-text :deep(p) {
  margin: 0 0 0.5em;
}

.message-text :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text :deep(ul),
.message-text :deep(ol) {
  margin: 0.35em 0 0.6em;
  padding-left: 1.5em;
}

.message-text :deep(li) {
  margin-bottom: 0.2em;
}

.message-text :deep(a) {
  color: var(--medical-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.message-text :deep(img) {
  max-width: 100%;
  height: auto;
}

.message-text :deep(pre),
.message-text :deep(code) {
  background: var(--medical-canvas);
}

.message-text :deep(pre) {
  max-width: 100%;
  margin: 0.6em 0;
  padding: 0.8em;
  border-radius: var(--medical-radius-sm);
  overflow-x: auto;
}

.message-text :deep(pre code) { background: transparent; }

.message-text :deep(table) {
  display: block;
  max-width: 100%;
  margin: 0.6em 0;
  border-collapse: collapse;
  overflow-x: auto;
}

.message-text :deep(th),
.message-text :deep(td) {
  padding: 0.4em 0.6em;
  border: 1px solid var(--medical-line);
  text-align: left;
}

.source-disclosure {
  margin-top: 8px;
  overflow: hidden;
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-sm);
  background: color-mix(in srgb, var(--medical-surface) 82%, transparent);
}

.source-disclosure summary {
  min-height: 44px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  color: var(--medical-ink-soft);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
  user-select: none;
}

.source-disclosure summary::-webkit-details-marker {
  display: none;
}

.source-disclosure summary::before {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-right: 1.5px solid currentColor;
  border-bottom: 1.5px solid currentColor;
  content: '';
  transform: rotate(-45deg);
  transition: transform var(--medical-duration-short) var(--medical-ease-out);
}

.source-disclosure[open] summary::before {
  transform: rotate(45deg) translate(-2px, -2px);
}

.source-disclosure summary:hover {
  background: var(--medical-surface-blue);
  color: var(--medical-accent);
}

.source-disclosure summary:focus-visible {
  outline: 2px solid var(--medical-focus);
  outline-offset: -2px;
}

.source-count {
  margin-left: auto;
  color: var(--medical-muted);
  font-size: 12px;
  font-weight: 500;
}

.source-content {
  padding: 10px 12px 12px;
  border-top: 1px solid var(--medical-line);
  background: var(--medical-surface);
  font-size: 12px;
  line-height: 1.6;
}

.source-content :deep(a) {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.message-time {
  color: var(--medical-muted);
  font-size: 11px;
  text-align: right;
}

.message-assistant .message-time {
  display: none;
}

.message-pending {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 28px;
  color: var(--medical-ink-soft);
  font-size: 13px;
}

.pending-dots {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.message-pending i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--medical-muted);
  animation: pending-pulse 1.2s infinite alternate;
}

.message-pending i:nth-child(2) { animation-delay: 0.2s; }
.message-pending i:nth-child(3) { animation-delay: 0.4s; }

.pending-label {
  line-height: 1.35;
}

@keyframes pending-pulse {
  to { opacity: 0.35; }
}

.input-section {
  display: block;
  padding: 8px clamp(20px, 4vw, 52px) 12px;
  border: 0;
  border-top: 1px solid var(--medical-line);
  border-radius: 0;
  background: var(--medical-surface);
  backdrop-filter: none;
}

.input-container {
  width: min(100%, 900px);
  min-height: 52px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 8px;
  margin: 0 auto;
  padding: 5px 6px 5px 12px;
  border: 1px solid var(--medical-line-strong);
  border-radius: 16px;
  background: var(--medical-surface);
  box-shadow: 0 2px 10px var(--medical-shadow);
}

.input-container:focus-within {
  border-color: var(--medical-focus);
  outline: 2px solid var(--medical-focus);
  outline-offset: 1px;
}

:deep(.el-textarea__inner) {
  min-height: 40px !important;
  max-height: 104px;
  padding: 9px 2px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: var(--medical-ink);
  font-family: var(--medical-font-body);
  font-size: 14px;
  line-height: 1.5;
  transition: none;
}

:deep(.el-textarea__inner:focus) {
  border: 0;
  background: transparent;
  box-shadow: none;
}

:deep(.el-textarea__inner::placeholder) {
  color: var(--medical-muted);
}

.composer-toolbar {
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0;
}

.langchain-button {
  min-height: 40px;
  display: inline-flex;
  justify-content: center;
  gap: 6px;
  padding: 0 12px;
  border-radius: var(--medical-radius-sm);
  font-size: 13px;
  transition: transform var(--medical-duration-short) var(--medical-ease-out),
    background-color var(--medical-duration-short) var(--medical-ease-out);
  white-space: nowrap;
}

.langchain-button::before { display: none; }

.langchain-button.primary {
  min-width: 78px;
  background: var(--medical-accent);
  color: var(--medical-accent-ink);
  box-shadow: none;
}

.langchain-button.primary:hover {
  background: var(--medical-accent-hover);
  color: var(--medical-accent-ink);
  box-shadow: none;
  transform: translateY(-1px);
}

.langchain-button.secondary {
  border: 1px solid var(--medical-line);
  background: var(--medical-surface);
  color: var(--medical-ink-soft);
  box-shadow: none;
}

.langchain-button.secondary:hover {
  border-color: var(--medical-line-strong);
  background: var(--medical-surface-blue);
  color: var(--medical-ink);
  box-shadow: none;
  transform: none;
}

.langchain-button:active,
.new-conversation-btn:active,
.sidebar-logout:active {
  transform: translateY(1px);
}

.langchain-style :is(button, a):focus-visible,
.langchain-style :deep(.el-button:focus-visible) {
  outline: 2px solid var(--medical-focus);
  outline-offset: 2px;
}

.langchain-style :deep(.el-button.is-disabled) {
  opacity: 0.5;
  cursor: not-allowed;
}

.sidebar-toggle,
.sidebar-scrim {
  display: none;
}

.upload-overlay {
  position: fixed;
  z-index: 40;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--medical-overlay);
  backdrop-filter: blur(3px);
}

.upload-dialog {
  width: min(420px, calc(100% - 32px));
  min-width: 0;
  padding: 32px;
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-lg);
  background: var(--medical-surface);
  box-shadow: 0 16px 48px var(--medical-shadow);
  text-align: center;
  animation: none;
}

.upload-icon { margin-bottom: 16px; color: var(--medical-accent); animation: none; }
.upload-text { margin-bottom: 20px; color: var(--medical-ink); }
.upload-text h3 { margin: 0 0 6px; text-shadow: none; }
.upload-text p { color: var(--medical-ink-soft); opacity: 1; }
.upload-progress { width: 100%; }
.upload-progress :deep(.el-progress-bar__outer) { background: var(--medical-line); }
.upload-progress :deep(.el-progress-bar__inner) { background: var(--medical-accent); }

@media (max-width: 800px) {
  .sidebar-toggle {
    width: 36px;
    height: 36px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 0;
    border: 1px solid var(--medical-line);
    border-radius: var(--medical-radius-sm);
    background: var(--medical-surface);
  }
  .chat-sidebar-toggle {
    position: absolute;
    z-index: 10;
    top: 12px;
    left: 12px;
    box-shadow: 0 2px 8px var(--medical-shadow);
  }
  .sidebar-toggle span {
    width: 16px;
    height: 1.5px;
    background: var(--medical-ink);
  }
  .main-content { display: block; }
  .sidebar {
    position: fixed;
    z-index: 12;
    top: 0;
    bottom: 0;
    left: 0;
    width: min(320px, 84vw);
    height: auto;
    transform: translateX(-100%);
    visibility: hidden;
    transition: transform var(--medical-duration-short) var(--medical-ease-out);
  }
  .sidebar.sidebar-open { transform: translateX(0); visibility: visible; }
  .sidebar-scrim {
    position: fixed;
    z-index: 11;
    inset: 0;
    display: block;
    width: 100%;
    border: 0;
    background: var(--medical-overlay);
  }
  .chat-area { width: 100%; }
  .messages-inner { padding: 60px var(--medical-space-md) var(--medical-space-md); }
  .input-section { padding: 8px var(--medical-space-md) 10px; }
}

@media (max-width: 520px) {
  .logo-text { font-size: 15px; }
  .logo-mark { width: 29px; height: 29px; font-size: 18px; }
  .message { max-width: 94%; }
  .message-user { max-width: 88%; padding: 7px 12px 5px; }
  .input-container { padding-left: 10px; gap: 5px; }
  .langchain-button { padding-inline: 10px; }
}

@media (max-width: 360px) {
  .logo-text { font-size: 14px; }
  .input-section { padding-inline: var(--medical-space-sm); }
  .composer-toolbar { gap: 4px; }
  .langchain-button { padding-inline: 7px; font-size: 11px; }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .langchain-button,
  .new-conversation-btn,
  .sidebar-logout,
  .message-pending i {
    animation: none;
    transition: none;
  }
}
</style>

<template>
  <div class="langchain-style">
    <!-- 顶部导航栏，与首页保持完全一致 -->
    <header class="langchain-header">
      <div class="header-content">
        <div class="logo">
          <span class="logo-mark" aria-hidden="true">✚</span>
          <span class="logo-text">智能医疗助手</span>
        </div>
        <div class="nav">
          <router-link to="/" class="nav-link">首页</router-link>
          <router-link to="/preferences" class="nav-link active">偏好设置</router-link>
        </div>
        <div class="user-info">
          <span class="user-id" v-if="user">{{ user.username }}</span>
          <el-button link class="logout-button" @click="handleLogout" v-if="user">
            登出
          </el-button>
        </div>
      </div>
    </header>

    <!-- 偏好设置主体 -->
    <main class="preferences-main">
      <div class="preferences-heading">
        <div class="heading-content">
          <h1>偏好设置</h1>
          <p>自定义您的智能医疗助手体验与临床咨询偏好</p>
        </div>
        <span class="heading-note">个人偏好 · 即时生效</span>
      </div>

      <div class="preferences-scroll-area">
        <div class="preferences-container">
          <!-- 卡片 1: 回答风格 -->
          <section class="pref-card">
            <div class="card-header">
              <div class="card-icon-badge">
                <el-icon :size="20"><ChatDotRound /></el-icon>
              </div>
              <div class="card-header-text">
                <h2>回答风格偏好</h2>
                <p>设置医疗咨询时智能助手的回复方式与偏好口吻</p>
              </div>
            </div>

            <div class="style-grid">
              <button
                v-for="item in styleOptions"
                :key="item.value"
                type="button"
                class="style-card"
                :class="{ active: preferredStyle === item.value }"
                @click="preferredStyle = item.value"
              >
                <div class="style-card-header">
                  <span class="style-card-title">{{ item.label }}</span>
                  <span class="style-card-radio"></span>
                </div>
                <p class="style-card-desc">{{ item.desc }}</p>
              </button>
            </div>

            <div class="card-footer">
              <div class="style-select-wrap">
                <span class="select-label">当前选择：</span>
                <el-select
                  v-model="preferredStyle"
                  placeholder="选择回答风格"
                  class="style-select"
                >
                  <el-option
                    v-for="opt in styleOptions"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
              </div>
              <button
                type="button"
                class="langchain-button primary"
                :disabled="savingStyle || !preferredStyle"
                @click="saveStyle"
              >
                <span v-if="savingStyle">保存中...</span>
                <span v-else>保存风格</span>
              </button>
            </div>
          </section>

          <!-- 卡片 2: 医疗过敏史 -->
          <section class="pref-card">
            <div class="card-header">
              <div class="card-icon-badge warning">
                <el-icon :size="20"><FirstAidKit /></el-icon>
              </div>
              <div class="card-header-text">
                <h2>个人用药与过敏史</h2>
                <p>记录您的药物过敏原，AI 医生诊断和推荐用药方案时将重点避开</p>
              </div>
            </div>

            <div class="quick-tags">
              <span class="quick-tags-label">常见快捷标签：</span>
              <div class="tag-chips">
                <button
                  v-for="tag in commonAllergies"
                  :key="tag"
                  type="button"
                  class="tag-chip"
                  @click="appendTag(tag)"
                >
                  + {{ tag }}
                </button>
              </div>
            </div>

            <div class="input-wrap">
              <el-input
                v-model="allergies"
                type="textarea"
                :rows="3"
                placeholder="请输入您的过敏史或用药禁忌，例如：青霉素过敏、对布洛芬等NSAIDs非甾体抗炎药胃部不适、阿司匹林哮喘等..."
                maxlength="500"
                show-word-limit
              />
            </div>

            <div class="card-footer align-end">
              <button
                type="button"
                class="langchain-button primary"
                :disabled="savingAllergies"
                @click="saveAllergies"
              >
                <span v-if="savingAllergies">保存中...</span>
                <span v-else>保存过敏史</span>
              </button>
            </div>
          </section>

          <!-- 卡片 3: 账户与记忆库状态 -->
          <section class="pref-card">
            <div class="card-header">
              <div class="card-icon-badge account">
                <el-icon :size="20"><User /></el-icon>
              </div>
              <div class="card-header-text">
                <h2>账户与长时记忆库</h2>
                <p>偏好数据已持久化关联至当前用户的专属医疗记忆存储空间</p>
              </div>
            </div>

            <div class="account-info-grid">
              <div class="account-info-item">
                <span class="info-label">登录用户名</span>
                <span class="info-val font-semibold">{{ username || '已登录用户' }}</span>
              </div>
              <div class="account-info-item">
                <span class="info-label">用户唯一标识</span>
                <span class="info-val">{{ userId || '-' }}</span>
              </div>
              <div class="account-info-item">
                <span class="info-label">记忆存储区</span>
                <span class="info-val">user_preference (PostgresStore)</span>
              </div>
              <div class="account-info-item">
                <span class="info-label">状态</span>
                <span class="info-status">
                  <span class="status-dot"></span>
                  已就绪 · 实时同步
                </span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useRouter } from 'vue-router'

const router = useRouter()

const user = ref<{ id: number; username: string } | null>(null)
const username = ref('')
const userId = ref('')
const preferredStyle = ref('友好')
const allergies = ref('')
const savingStyle = ref(false)
const savingAllergies = ref(false)

const backendUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'

const styleOptions = [
  {
    label: '简洁',
    value: '简洁',
    desc: '要点精炼直截了当，快速掌握关键用药与诊断建议'
  },
  {
    label: '友好',
    value: '友好',
    desc: '亲切关怀、通俗易懂，富有人文关怀与家庭医生温度'
  },
  {
    label: '专业',
    value: '专业',
    desc: '严密细致、临床循证视角，带有详尽医学术语解释'
  },
  {
    label: '详细',
    value: '详细',
    desc: '深入全面阐述病因、发病机制、护理细节与用药禁忌'
  }
]

const commonAllergies = [
  '青霉素过敏',
  '头孢类抗生素过敏',
  '阿司匹林哮喘',
  '布洛芬/NSAIDs不耐受',
  '磺胺类药物过敏',
  '无已知药物过敏'
]

const appendTag = (tag: string) => {
  if (tag === '无已知药物过敏') {
    allergies.value = tag
    return
  }
  if (!allergies.value) {
    allergies.value = tag
  } else if (!allergies.value.includes(tag)) {
    if (allergies.value === '无已知药物过敏') {
      allergies.value = tag
    } else {
      allergies.value = `${allergies.value}，${tag}`
    }
  }
}

// 检查登录状态
const checkLoginStatus = () => {
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  if (!token || !userStr) {
    router.push('/login')
    return
  }
  try {
    const savedUser = JSON.parse(userStr) as { id: number; username: string }
    user.value = savedUser
    username.value = savedUser.username || ''
    userId.value = 'user_' + savedUser.id
  } catch {
    router.push('/login')
  }
}

// 加载偏好设置
const loadPreferences = async () => {
  try {
    const token = localStorage.getItem('token')
    if (!token) return
    const response = await axios.get(`${backendUrl}/preferences/list`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    })

    // 优先从返回的 data 字典解析
    if (response.data && response.data.data) {
      const data = response.data.data
      if (data.preferred_style) {
        preferredStyle.value = data.preferred_style
      }
      if (data.allergies) {
        allergies.value = data.allergies
      }
    } else if (response.data && response.data.preferences) {
      // 兼容字符串解析
      const prefs = response.data.preferences
      const prefLines = prefs.split('\n')
      prefLines.forEach((line: string) => {
        const [key, ...rest] = line.split(': ')
        const value = rest.join(': ')
        if (key === 'preferred_style') {
          preferredStyle.value = value
        } else if (key === 'allergies') {
          allergies.value = value
        }
      })
    }
  } catch (error) {
    console.error('加载偏好失败:', error)
  }
}

// 保存风格
const saveStyle = async () => {
  if (!preferredStyle.value) return
  savingStyle.value = true
  try {
    const token = localStorage.getItem('token')
    await axios.post(
      `${backendUrl}/preferences/save`,
      {
        key: 'preferred_style',
        value: preferredStyle.value
      },
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    )
    ElMessage.success(`回答风格已更新为：${preferredStyle.value}`)
  } catch (error) {
    console.error('保存风格失败:', error)
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    savingStyle.value = false
  }
}

// 保存过敏史
const saveAllergies = async () => {
  savingAllergies.value = true
  try {
    const token = localStorage.getItem('token')
    await axios.post(
      `${backendUrl}/preferences/save`,
      {
        key: 'allergies',
        value: allergies.value
      },
      {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      }
    )
    ElMessage.success('过敏史偏好已成功保存')
  } catch (error) {
    console.error('保存过敏史失败:', error)
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    savingAllergies.value = false
  }
}

// 登出
const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  user.value = null
  router.push('/login')
  ElMessage.success('已安全退出登录')
}

onMounted(() => {
  checkLoginStatus()
  loadPreferences()
})
</script>

<style scoped>
.langchain-style {
  --el-color-primary: var(--medical-accent);
  width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  display: grid;
  grid-template-rows: 64px minmax(0, 1fr);
  overflow: hidden;
  background: var(--medical-canvas);
  color: var(--medical-ink);
  font-family: var(--medical-font-body);
}

/* 顶部导航栏，完全对齐首页设计 */
.langchain-header {
  position: relative;
  top: auto;
  z-index: 20;
  height: 64px;
  background: var(--medical-surface);
  border-bottom: 1px solid var(--medical-line);
}

.header-content {
  width: 100%;
  max-width: none;
  height: 100%;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--medical-space-lg);
  margin: 0;
  padding: 0 var(--medical-space-lg);
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--medical-space-sm);
  min-width: 0;
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
  font-family: var(--medical-font-display);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.02em;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav {
  display: flex;
  justify-self: center;
  align-items: center;
  gap: var(--medical-space-xl);
  height: 100%;
}

.nav-link {
  height: 100%;
  display: inline-flex;
  align-items: center;
  color: var(--medical-ink-soft);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  position: relative;
  transition: color var(--medical-duration-short) var(--medical-ease-out);
  white-space: nowrap;
}

.nav-link:hover,
.nav-link.active {
  color: var(--medical-accent);
}

.nav-link.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: var(--medical-accent);
  border-radius: 0;
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--medical-space-sm);
}

.user-id {
  margin: 0;
  padding: 6px 10px;
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-sm);
  background: var(--medical-surface-blue);
  color: var(--medical-ink-soft);
  font-size: 13px;
}

.logout-button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-sm);
  background: var(--medical-surface);
  color: var(--medical-ink-soft);
  cursor: pointer;
  transition: color var(--medical-duration-short) var(--medical-ease-out),
    background-color var(--medical-duration-short) var(--medical-ease-out);
}

.logout-button:hover {
  border-color: var(--medical-line-strong);
  background: var(--medical-surface-blue);
  color: var(--medical-ink);
}

/* 主内容区域 */
.preferences-main {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--medical-canvas);
}

.preferences-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--medical-space-md);
  min-height: 70px;
  padding: 12px var(--medical-space-xl);
  border-bottom: 1px solid var(--medical-line);
  background: var(--medical-surface);
  flex: none;
}

.heading-content h1 {
  margin: 0;
  font-family: var(--medical-font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--medical-ink);
}

.heading-content p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--medical-muted);
}

.heading-note {
  border: 1px solid var(--medical-line);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--medical-muted);
  background: var(--medical-surface-blue);
  white-space: nowrap;
}

/* 可滚动的偏好设置容器 */
.preferences-scroll-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 20px 48px;
}

.preferences-container {
  max-width: 840px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 偏好卡片 */
.pref-card {
  background: var(--medical-surface);
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-lg);
  box-shadow: 0 2px 8px var(--medical-shadow);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  transition: border-color var(--medical-duration-short) var(--medical-ease-out);
}

.pref-card:hover {
  border-color: var(--medical-line-strong);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 14px;
}

.card-icon-badge {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: var(--medical-radius-md);
  background: var(--medical-surface-blue);
  color: var(--medical-accent);
  flex: none;
}

.card-icon-badge.warning {
  background: oklch(96% 0.04 40);
  color: oklch(55% 0.18 40);
}

.card-icon-badge.account {
  background: oklch(95% 0.03 200);
  color: oklch(50% 0.15 200);
}

.card-header-text h2 {
  margin: 0;
  font-family: var(--medical-font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--medical-ink);
}

.card-header-text p {
  margin: 3px 0 0;
  font-size: 13px;
  color: var(--medical-muted);
}

/* 风格选择卡片网格 */
.style-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.style-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-md);
  background: var(--medical-surface);
  text-align: left;
  cursor: pointer;
  transition: all var(--medical-duration-short) var(--medical-ease-out);
}

.style-card:hover {
  border-color: var(--medical-accent);
  background: var(--medical-surface-blue);
}

.style-card.active {
  border-color: var(--medical-accent);
  background: var(--medical-surface-blue);
  box-shadow: 0 0 0 1px var(--medical-accent) inset;
}

.style-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.style-card-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--medical-ink);
}

.style-card.active .style-card-title {
  color: var(--medical-accent);
}

.style-card-radio {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1.5px solid var(--medical-line-strong);
  display: grid;
  place-items: center;
  transition: all var(--medical-duration-short) var(--medical-ease-out);
}

.style-card.active .style-card-radio {
  border-color: var(--medical-accent);
  background: var(--medical-accent);
}

.style-card.active .style-card-radio::after {
  content: '';
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #ffffff;
}

.style-card-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--medical-ink-soft);
}

/* 标签推荐 */
.quick-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.quick-tags-label {
  font-size: 12px;
  color: var(--medical-muted);
}

.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-chip {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--medical-line);
  border-radius: 999px;
  background: var(--medical-surface-blue);
  color: var(--medical-ink-soft);
  cursor: pointer;
  transition: all var(--medical-duration-short) var(--medical-ease-out);
}

.tag-chip:hover {
  border-color: var(--medical-accent);
  color: var(--medical-accent);
  background: var(--medical-surface);
}

/* 输入框定制 */
.input-wrap :deep(.el-textarea__inner) {
  padding: 12px;
  border-radius: var(--medical-radius-md);
  border: 1px solid var(--medical-line);
  background: var(--medical-surface);
  color: var(--medical-ink);
  font-family: var(--medical-font-body);
  font-size: 13px;
  line-height: 1.6;
  box-shadow: none;
  transition: border-color var(--medical-duration-short) var(--medical-ease-out);
}

.input-wrap :deep(.el-textarea__inner:focus) {
  border-color: var(--medical-focus);
  box-shadow: 0 0 0 2px var(--medical-surface-blue);
}

/* 账户信息网格 */
.account-info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  padding: 14px;
  background: var(--medical-canvas);
  border: 1px solid var(--medical-line);
  border-radius: var(--medical-radius-md);
}

.account-info-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.info-label {
  font-size: 11px;
  color: var(--medical-muted);
}

.info-val {
  font-size: 13px;
  color: var(--medical-ink);
}

.font-semibold {
  font-weight: 600;
}

.info-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: oklch(50% 0.16 145);
  font-weight: 500;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: oklch(62% 0.19 145);
}

/* 底部操作区 */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--medical-line);
}

.card-footer.align-end {
  justify-content: flex-end;
}

.style-select-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.select-label {
  font-size: 13px;
  color: var(--medical-muted);
}

.style-select {
  width: 120px;
}

.style-select :deep(.el-select__wrapper) {
  border-radius: var(--medical-radius-sm);
  background-color: var(--medical-surface);
  box-shadow: 0 0 0 1px var(--medical-line) inset;
}

.style-select :deep(.el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px var(--medical-focus) inset;
}

/* 统一按钮样式，与首页一致 */
.langchain-button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 16px;
  border-radius: var(--medical-radius-sm);
  font-size: 13px;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
  transition: transform var(--medical-duration-short) var(--medical-ease-out),
    background-color var(--medical-duration-short) var(--medical-ease-out);
  white-space: nowrap;
}

.langchain-button.primary {
  min-width: 86px;
  background: var(--medical-accent);
  color: var(--medical-accent-ink);
  box-shadow: none;
}

.langchain-button.primary:hover:not(:disabled) {
  background: var(--medical-accent-hover);
  transform: translateY(-1px);
}

.langchain-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.langchain-button:active:not(:disabled),
.logout-button:active {
  transform: translateY(1px);
}

/* 响应式支持 */
@media (max-width: 800px) {
  .langchain-style {
    grid-template-rows: 58px minmax(0, 1fr);
  }

  .header-content {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: var(--medical-space-sm);
    padding: 0 var(--medical-space-md);
  }

  .style-grid {
    grid-template-columns: 1fr;
  }

  .account-info-grid {
    grid-template-columns: 1fr;
  }

  .card-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .style-select-wrap {
    justify-content: space-between;
  }

  .card-footer.align-end {
    align-items: stretch;
  }

  .card-footer .langchain-button {
    width: 100%;
  }
}

@media (max-width: 520px) {
  .logo-text {
    font-size: 15px;
  }

  .logo-mark {
    width: 29px;
    height: 29px;
    font-size: 18px;
  }

  .user-info {
    display: none;
  }

  .heading-note {
    display: none;
  }

  .preferences-heading {
    min-height: 58px;
    padding: 8px var(--medical-space-md);
  }

  .pref-card {
    padding: 16px;
  }
}
</style>

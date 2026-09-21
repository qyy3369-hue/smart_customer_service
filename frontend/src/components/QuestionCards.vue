<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

export interface IntakeQuestion {
  id: string
  title: string
  hint: string
  options: Array<{ value: string; label: string }>
}

export interface IntakeAnswer {
  choices: string[]
  other_text: string
}

const props = defineProps<{ questions: IntakeQuestion[]; busy?: boolean }>()
const emit = defineEmits<{ submit: [answers: Record<string, IntakeAnswer>] }>()
const selected = reactive<Record<string, string[]>>({})
const otherText = reactive<Record<string, string>>({})
const attempted = ref(false)
const submitted = ref(false)

watch(() => props.questions, (questions) => {
  attempted.value = false
  submitted.value = false
  for (const key of Object.keys(selected)) delete selected[key]
  for (const key of Object.keys(otherText)) delete otherText[key]
  for (const question of questions) {
    selected[question.id] = []
    otherText[question.id] = ''
  }
}, { immediate: true })

watch(() => props.busy, (busy) => {
  if (!busy) submitted.value = false
})

const toggle = (id: string, value: string) => {
  if (props.busy) return
  const choices = selected[id] || []
  if (choices.includes(value)) {
    selected[id] = choices.filter((choice) => choice !== value)
  } else if (value === 'none' || value === 'unsure') {
    selected[id] = [value]
  } else {
    selected[id] = [...choices.filter((choice) => choice !== 'none' && choice !== 'unsure'), value]
  }
}

const invalid = (question: IntakeQuestion) => {
  const choices = selected[question.id] || []
  return choices.length === 0 || (choices.includes('other') && !otherText[question.id]?.trim())
}

const submit = () => {
  attempted.value = true
  if (props.busy || props.questions.some(invalid)) return
  submitted.value = true
  emit('submit', Object.fromEntries(props.questions.map((question) => [question.id, {
    choices: [...(selected[question.id] || [])],
    other_text: otherText[question.id]?.trim() || ''
  }])))
}
</script>

<template>
  <section class="intake-panel" aria-label="补充症状信息">
    <div class="intake-header">
      <div>
        <span class="intake-eyebrow">问诊补充</span>
        <h2>先了解你的具体情况</h2>
      </div>
      <span class="intake-count">{{ questions.length }} 个问题 · 可多选</span>
    </div>
    <div class="intake-list">
      <div v-for="(question, index) in questions" :key="question.id" class="intake-card"
        role="group" :aria-labelledby="`intake-title-${question.id}`">
        <div class="intake-question-head">
          <span class="intake-number">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h3 :id="`intake-title-${question.id}`">{{ question.title }}</h3>
            <p>{{ question.hint }}</p>
          </div>
        </div>
        <div class="intake-options">
          <button v-for="option in question.options" :key="option.value" type="button"
            class="intake-option" :class="{ 'is-selected': selected[question.id]?.includes(option.value) }"
            :aria-pressed="selected[question.id]?.includes(option.value)" :disabled="busy"
            @click="toggle(question.id, option.value)">
            <span class="option-indicator" aria-hidden="true">{{ selected[question.id]?.includes(option.value) ? '✓' : '+' }}</span>
            {{ option.label }}
          </button>
        </div>
        <label v-if="selected[question.id]?.includes('other')" class="intake-other">
          <span>补充说明</span>
          <textarea v-model="otherText[question.id]" rows="2" maxlength="300" :disabled="busy"
            :aria-invalid="attempted && !otherText[question.id]?.trim()" placeholder="用自己的话描述即可" />
        </label>
        <p v-if="attempted && invalid(question)" class="intake-error" role="alert">
          {{ selected[question.id]?.includes('other') ? '请填写“其他”的具体情况。' : '请至少选择一项。' }}
        </p>
      </div>
    </div>
    <div class="intake-footer">
      <p>所选内容将一起提交。</p>
      <button type="button" class="intake-submit" :class="{ 'is-success': submitted }"
        :disabled="busy || submitted" @click="submit">
        {{ submitted ? '✓ 已提交，正在处理' : '提交回答' }} <span v-if="!submitted" aria-hidden="true">→</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
/* Hallmark · component: intake cards · genre: modern-minimal · theme: existing medical blue-white
 * states: default · hover · focus · active · disabled · loading · error · success
 * contrast: inherited from medical tokens
 */
.intake-panel { align-self: stretch; border: 1px solid var(--medical-line); border-radius: var(--medical-radius-lg); background: var(--medical-surface); color: var(--medical-ink); overflow: hidden; box-shadow: 0 8px 24px var(--medical-shadow); }
.intake-header { display: flex; justify-content: space-between; gap: 16px; align-items: end; padding: 20px 22px; border-bottom: 1px solid var(--medical-line); background: var(--medical-surface-blue); }
.intake-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .08em; color: var(--medical-accent); }
.intake-header h2 { margin: 6px 0 0; font-family: var(--medical-font-display); font-size: 19px; line-height: 1.3; font-style: normal; }
.intake-count { color: var(--medical-ink-soft); font-size: 12px; white-space: nowrap; }
.intake-list { display: grid; gap: 0; }
.intake-card { padding: 20px 22px; border-bottom: 1px solid var(--medical-line); }
.intake-question-head { display: flex; gap: 12px; align-items: start; }
.intake-number { color: var(--medical-accent); font-size: 12px; font-weight: 700; padding-top: 3px; }
.intake-card h3 { margin: 0; font-size: 15px; line-height: 1.5; font-weight: 650; }
.intake-card p { margin: 3px 0 0; font-size: 12px; color: var(--medical-ink-soft); }
.intake-options { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 15px; }
.intake-option { min-height: 44px; display: inline-flex; align-items: center; gap: 7px; padding: 8px 13px; border: 1px solid var(--medical-line-strong); border-radius: 999px; background: var(--medical-surface); color: var(--medical-ink); font: inherit; font-size: 13px; cursor: pointer; transition: background-color var(--medical-duration-short), border-color var(--medical-duration-short); white-space: nowrap; }
.intake-option:hover:not(:disabled) { background: var(--medical-surface-blue); }
.intake-option:focus-visible, .intake-submit:focus-visible, .intake-other textarea:focus-visible { outline: 2px solid var(--medical-focus); outline-offset: 2px; }
.intake-option:active:not(:disabled), .intake-submit:active:not(:disabled) { transform: translateY(1px); }
.intake-option.is-selected { border-color: var(--medical-accent); background: var(--medical-user-bubble); color: var(--medical-ink); }
.intake-option:disabled, .intake-submit:disabled { opacity: .55; cursor: not-allowed; }
.option-indicator { display: inline-grid; place-items: center; width: 16px; height: 16px; border: 1px solid currentColor; border-radius: 4px; font-size: 11px; line-height: 1; }
.intake-other { display: grid; gap: 7px; margin-top: 14px; font-size: 12px; font-weight: 600; }
.intake-other textarea { width: 100%; min-height: 74px; resize: vertical; padding: 10px 12px; border: 1px solid var(--medical-line-strong); border-radius: var(--medical-radius-sm); background: var(--medical-surface); color: var(--medical-ink); font: inherit; font-weight: 400; }
.intake-other textarea[aria-invalid="true"] { border-color: var(--medical-danger); }
.intake-card .intake-error { min-height: 1lh; margin-top: 8px; color: var(--medical-danger); }
.intake-footer { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 14px 22px; }
.intake-footer p { margin: 0; color: var(--medical-ink-soft); font-size: 12px; }
.intake-submit { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 14px; padding: 0 17px; border: 1px solid var(--medical-accent); border-radius: var(--medical-radius-sm); background: var(--medical-accent); color: var(--medical-accent-ink); font: inherit; font-size: 13px; font-weight: 650; white-space: nowrap; cursor: pointer; }
.intake-submit:hover:not(:disabled) { background: var(--medical-accent-hover); }
.intake-submit.is-success { border-color: var(--medical-accent); background: var(--medical-user-bubble); color: var(--medical-ink); }
@media (max-width: 640px) { .intake-header, .intake-footer { align-items: start; flex-direction: column; } .intake-submit { align-self: stretch; } .intake-header, .intake-card, .intake-footer { padding-inline: 16px; } }
@media (prefers-reduced-motion: reduce) { .intake-option { transition: none; } }
</style>

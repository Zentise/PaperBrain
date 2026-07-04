// js/config.js — shared constants for both pages

export const API =
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : 'https://REPLACE_WITH_CLOUD_RUN_URL'

export const MODELS = [
  {
    id: 'google/gemini-2.5-flash-lite-preview-06-17',
    name: 'Gemini 2.5 Flash Lite', label: 'gemini',
    tier: 'fast', description: 'Fast, best for quick Q&A', context: '1M',
  },
  {
    id: 'meta-llama/llama-3.3-70b-instruct',
    name: 'Llama 3.3 70B', label: 'llama',
    tier: 'fast', description: 'Open source, free tier', context: '128k',
  },
  {
    id: 'deepseek/deepseek-chat-v3-0324',
    name: 'DeepSeek V3', label: 'deepseek',
    tier: 'balanced', description: 'Best quality/cost ratio', context: '128k',
  },
  {
    id: 'anthropic/claude-sonnet-4-5',
    name: 'Claude Sonnet', label: 'claude',
    tier: 'balanced', description: 'Complex reasoning', context: '200k',
  },
  {
    id: 'openai/gpt-4o',
    name: 'GPT-4o', label: 'gpt4o',
    tier: 'powerful', description: 'Reliable, well-rounded', context: '128k',
  },
  {
    id: 'deepseek/deepseek-r1',
    name: 'DeepSeek R1', label: 'r1',
    tier: 'powerful', description: 'Shows reasoning steps', context: '128k',
  },
]

export const TIER_COLORS = {
  fast:     '#22c55e',
  balanced: '#e8a838',
  powerful: '#6e56cf',
}

export const DEFAULT_MODEL = MODELS[0]

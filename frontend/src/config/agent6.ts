export const AGENT6_CONFIG = {
    modelName: import.meta.env.VITE_MODEL_NAME ?? 'Qwen3.5-397B-A17B',
    baseUrl: (import.meta.env.VITE_AGENT6_BASE_URL ?? '').replace(/\/$/, ''),
    apiPrefix: import.meta.env.VITE_AGENT6_API_PREFIX ?? '/api/ad-intel',
} as const

export const AGENT6_ENDPOINTS = {
    run: '/run',
    taskStatus: (taskId: string) => `/task/${taskId}`,
    taskMeta: (taskId: string) => `/task/${taskId}/meta`,
    taskInsights: (taskId: string) => `/task/${taskId}/insights`,
} as const

export function buildAgent6Url(path: string): string {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    const basePath = `${AGENT6_CONFIG.apiPrefix}${normalizedPath}`
    return AGENT6_CONFIG.baseUrl ? `${AGENT6_CONFIG.baseUrl}${basePath}` : basePath
}

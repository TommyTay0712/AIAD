import { AGENT6_CONFIG, AGENT6_ENDPOINTS, buildAgent6Url } from '../config/agent6'

export type ApiErrorCode = 'timeout' | 'auth' | 'rate_limit' | 'server_error' | 'network_error' | 'unknown'

export class ApiRequestError extends Error {
    code: ApiErrorCode
    status: number
    details?: unknown

    constructor(message: string, code: ApiErrorCode, status = 0, details?: unknown) {
        super(message)
        this.name = 'ApiRequestError'
        this.code = code
        this.status = status
        this.details = details
    }
}

function classifyStatusCode(status: number): ApiErrorCode {
    if (status === 401 || status === 403) return 'auth'
    if (status === 429) return 'rate_limit'
    if (status >= 500) return 'server_error'
    return 'unknown'
}

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 20000)
    const headers = {
        'Content-Type': 'application/json',
        'X-AI-Model': AGENT6_CONFIG.modelName,
        ...(options.headers || {}),
    }

    try {
        const response = await fetch(buildAgent6Url(path), {
            ...options,
            headers,
            signal: controller.signal,
        })

        const rawText = await response.text()
        const parsed = rawText ? JSON.parse(rawText) : {}

        if (!response.ok) {
            throw new ApiRequestError(
                `请求失败(${response.status})`,
                classifyStatusCode(response.status),
                response.status,
                parsed,
            )
        }

        return parsed as T
    } catch (error) {
        if (error instanceof ApiRequestError) {
            throw error
        }
        if (error instanceof DOMException && error.name === 'AbortError') {
            throw new ApiRequestError('请求超时，请稍后重试。', 'timeout')
        }
        throw new ApiRequestError('网络异常，请检查连接。', 'network_error')
    } finally {
        clearTimeout(timeout)
    }
}

export type RunTaskPayload = {
    ad_type: string
    keywords: string[]
    platform: string
    limit: number
    max_comments_per_note: number
    enable_media_download: boolean
    time_range: string
}

export async function submitTask(payload: RunTaskPayload) {
    return requestJson<{ task_id?: string } & Record<string, unknown>>(AGENT6_ENDPOINTS.run, {
        method: 'POST',
        body: JSON.stringify(payload),
    })
}

export async function getTaskStatus(taskId: string) {
    return requestJson<Record<string, unknown>>(AGENT6_ENDPOINTS.taskStatus(taskId))
}

export async function getTaskMeta(taskId: string) {
    return requestJson<Record<string, unknown>>(AGENT6_ENDPOINTS.taskMeta(taskId))
}

export async function getTaskInsights(taskId: string) {
    return requestJson<Record<string, unknown>>(AGENT6_ENDPOINTS.taskInsights(taskId))
}

export async function waitTaskDone(
    taskId: string,
    onPoll?: (pollCount: number, status: string) => void,
    maxAttempts = 180,
    sleepMs = 3000,
) {
    for (let i = 0; i < maxAttempts; i += 1) {
        const task = await getTaskStatus(taskId)
        const currentStatus = String(task.status || 'success')
        if (onPoll) onPoll(i + 1, currentStatus)
        if (!task.status || currentStatus === 'success' || currentStatus === 'failed') {
            return task
        }
        await new Promise((resolve) => setTimeout(resolve, sleepMs))
    }
    throw new ApiRequestError('任务轮询超时，请稍后重试。', 'timeout')
}

export function toUserErrorMessage(error: unknown): string {
    if (!(error instanceof ApiRequestError)) {
        return '请求失败，请稍后重试。'
    }
    const messageByCode: Record<ApiErrorCode, string> = {
        timeout: '请求超时，请点击重试。',
        auth: '鉴权失败，请重新登录后再试。',
        rate_limit: '请求过于频繁，请稍后再试。',
        server_error: '服务端异常，请稍后重试。',
        network_error: '网络异常，请检查网络连接。',
        unknown: '请求失败，请稍后重试。',
    }
    return messageByCode[error.code] || messageByCode.unknown
}

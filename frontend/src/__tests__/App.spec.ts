import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'
import { getTaskInsights, getTaskMeta } from '../services/adIntelApi'

vi.mock('../services/adIntelApi', () => ({
    getTaskInsights: vi.fn(),
    getTaskMeta: vi.fn(),
    streamTaskEvents: vi.fn(),
    submitTask: vi.fn(),
    toUserErrorMessage: vi.fn(() => '请求失败'),
}))

describe('App UI state loop', () => {
    it('shows idle state by default', () => {
        const wrapper = mount(App)

        expect(wrapper.text()).toContain('未开始')
        expect(wrapper.text()).toContain('等待启动')
    })

    it('updates state text when phase changes', async () => {
        const wrapper = mount(App)
            ; (wrapper.vm as any).setTaskPhase('error')
        await wrapper.vm.$nextTick()

        expect(wrapper.text()).toContain('失败')
        expect(wrapper.text()).toContain('任务执行失败')
    })

    it('copies generated ad text instead of dispatching', async () => {
        const writeText = vi.fn().mockResolvedValue(undefined)
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText },
            configurable: true,
        })
        const wrapper = mount(App)

        await (wrapper.vm as any).dispatchAd({ ad_text: '这条文案用于复制' })

        expect(writeText).toHaveBeenCalledWith('这条文案用于复制')
        expect(wrapper.text()).toContain('AI 文案已复制')
    })

    it('refreshes review queue from insights', async () => {
        vi.mocked(getTaskInsights).mockResolvedValueOnce({
            review_queue: [
                {
                    comment_id: 'c1',
                    author: '博主A',
                    platform: '小红书',
                    source_text: '求推荐',
                    ad_text: '可以先看温和一点的方向',
                    predicted_affinity: 76,
                    focus: '品牌曝光',
                    sentiment: 'neutral',
                    comment_like_count: 12,
                    post_like_count: 100,
                    selection_reason: '高赞帖子 + 高赞评论',
                },
            ],
            comment_selection_meta: {
                selected_comments: 1,
                covered_posts: 1,
                valid_comments: 1,
                strategy_version: 'priority-comments-v1',
            },
        } as any)
        const wrapper = mount(App)
            ; (wrapper.vm as any).taskId = 'task-1'
            ; (wrapper.vm as any).activeScreen = 'review'

        await (wrapper.vm as any).loadInsights()
        await wrapper.vm.$nextTick()

        expect(getTaskInsights).toHaveBeenCalledWith('task-1')
        expect(wrapper.text()).toContain('高赞帖子 + 高赞评论')
        expect(wrapper.text()).toContain('priority-comments-v1')
    })

    it('loads an existing task by task_id query without running a new task', async () => {
        vi.mocked(getTaskMeta).mockResolvedValueOnce({ task_id: 'mock-priority-001' } as any)
        vi.mocked(getTaskInsights).mockResolvedValueOnce({
            review_queue: [],
            comment_selection_meta: {
                selected_comments: 0,
            },
        } as any)
        window.history.pushState({}, '', '/review_queue?task_id=mock-priority-001')

        const wrapper = mount(App)
        await new Promise((resolve) => setTimeout(resolve, 0))
        await wrapper.vm.$nextTick()

        expect((wrapper.vm as any).taskId).toBe('mock-priority-001')
        expect(getTaskMeta).toHaveBeenCalledWith('mock-priority-001')
        expect(getTaskInsights).toHaveBeenCalledWith('mock-priority-001')
        expect(wrapper.text()).toContain('成功')
    })
})

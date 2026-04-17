import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'

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
})

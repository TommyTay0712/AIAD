import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '../layouts/AppShell.vue'
import AnalyticsDashboardView from '../views/AnalyticsDashboardView.vue'
import CampaignSetupView from '../views/CampaignSetupView.vue'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: '/',
            component: AppShell,
            children: [
                {
                    path: '',
                    redirect: '/analytics-dashboard',
                },
                {
                    path: 'analytics-dashboard',
                    name: 'analytics-dashboard',
                    component: AnalyticsDashboardView,
                },
                {
                    path: 'campaign-setup',
                    name: 'campaign-setup',
                    component: CampaignSetupView,
                },
            ],
        },
    ],
})

export default router
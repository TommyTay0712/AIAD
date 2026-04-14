<script setup lang="ts">
import { reactive } from 'vue'
import { campaignDefaults } from '../data/mock'

const form = reactive({
  productName: campaignDefaults.productName,
  keyValue: campaignDefaults.keyValue,
  industry: campaignDefaults.industry,
  tone: campaignDefaults.tone,
})
</script>

<template>
  <section class="page-section">
    <div class="page-title-wrap">
      <h2>Campaign Configuration</h2>
      <p class="subtitle">Define intelligence parameters for your AI-powered outreach.</p>
    </div>

    <div class="setup-grid">
      <article class="panel">
        <h3>Product Identity</h3>
        <label class="field-label" for="productName">Product/Service Name</label>
        <input id="productName" v-model="form.productName" class="field-input" />

        <label class="field-label" for="keyValue">Key Value Proposition</label>
        <textarea id="keyValue" v-model="form.keyValue" class="field-input field-area" />
      </article>

      <article class="panel panel-accent">
        <h3>Scraping Parameters</h3>
        <div class="stats-row">
          <span>Source Intensity</span>
          <strong>250</strong>
        </div>
        <div class="stats-row">
          <span>Interaction Depth</span>
          <strong>15</strong>
        </div>
        <p class="mini-note">Model (planned): Qwen3.5-397B-A17B</p>
      </article>
    </div>
  </section>
</template>
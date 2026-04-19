<script setup lang="ts">
import { analyticsSummary } from '../data/mock'
</script>

<template>
  <section class="page-section">
    <div class="page-title-wrap">
      <p class="kicker">REPORT: Q3 ENGAGEMENT ANALYSIS</p>
      <h2>Analytics Dashboard</h2>
      <p class="subtitle">A comprehensive breakdown of architectural sentiment and performance metrics.</p>
    </div>

    <div class="metric-grid">
      <article class="metric-card">
        <p>Total Comments</p>
        <h3>{{ analyticsSummary.totalComments }}</h3>
      </article>
      <article class="metric-card">
        <p>Posts Analyzed</p>
        <h3>{{ analyticsSummary.postsAnalyzed }}</h3>
      </article>
      <article class="metric-card metric-card-accent">
        <p>Ad Insertion Efficiency</p>
        <h3>{{ analyticsSummary.adInsertionEfficiency }}</h3>
      </article>
    </div>

    <div class="panel-grid">
      <article class="panel panel-large">
        <h3>Topic Frequency</h3>
        <div class="tag-cloud">
          <span>Architecture</span>
          <span>AI Generative</span>
          <span>Smart Cities</span>
          <span>Sustainability</span>
          <span>Modular Design</span>
        </div>
      </article>
      <article class="panel">
        <h3>Sentiment Index</h3>
        <p>Positive 65%</p>
        <p>Neutral 25%</p>
        <p>Negative 10%</p>
      </article>
    </div>
  </section>
</template>
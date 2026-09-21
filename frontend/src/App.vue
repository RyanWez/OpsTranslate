<script setup lang="ts">
import {
  NConfigProvider,
  darkTheme,
  NMessageProvider,
  NDialogProvider,
  NNotificationProvider,
  NLoadingBarProvider,
  GlobalThemeOverrides,
} from 'naive-ui'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#10b981',
    primaryColorHover: '#34d399',
    primaryColorPressed: '#059669',
    primaryColorSuppl: '#10b981',
    infoColor: '#06b6d4',
    successColor: '#10b981',
    warningColor: '#f59e0b',
    errorColor: '#ef4444',
    bodyColor: '#0b0f19',
    cardColor: 'rgba(17, 24, 39, 0.75)',
    modalColor: '#111827',
    textColorBase: '#f3f4f6',
    textColor1: '#f9fafb',
    textColor2: '#e5e7eb',
    textColor3: '#9ca3af',
    borderColor: 'rgba(255, 255, 255, 0.08)',
    fontFamily: 'Inter, system-ui, sans-serif',
    fontFamilyMono: 'JetBrains Mono, monospace',
    borderRadius: '8px',
  },
  Card: {
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  DataTable: {
    thColor: '#111827',
    tdColor: 'transparent',
    tdColorHover: 'rgba(255, 255, 255, 0.03)',
    borderColor: 'rgba(255, 255, 255, 0.06)',
  },
  Menu: {
    itemTextColorHoverHorizontal: '#10b981',
    itemTextColorActive: '#10b981',
    itemIconColorActive: '#10b981',
  },
}
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NLoadingBarProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <NMessageProvider>
            <router-view />
          </NMessageProvider>
        </NNotificationProvider>
      </NDialogProvider>
    </NLoadingBarProvider>
  </NConfigProvider>
</template>

<style>
/* Global background ensure */
html, body, #app {
  height: 100%;
  margin: 0;
  padding: 0;
  background-color: #0b0f19;
}
</style>

import { ref, onMounted, onUnmounted } from 'vue'

export function useMobile(breakpoint = 640) {
  const isMobile = ref(typeof window !== 'undefined' ? window.innerWidth < breakpoint : false)

  function update() {
    isMobile.value = window.innerWidth < breakpoint
  }

  onMounted(() => {
    update()
    window.addEventListener('resize', update, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('resize', update)
  })

  return { isMobile }
}

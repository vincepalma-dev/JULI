import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../src/App.vue'

describe('App', () => {
  it('mounts the whole dashboard and asks for a session when there is no token', () => {
    const wrapper = mount(App, { attachTo: document.body })
    expect(wrapper.find('[role="alert"]').text()).toContain('No session.')
    expect(fetch).not.toHaveBeenCalled() // nothing is requested without a token
    wrapper.unmount()
  })
})

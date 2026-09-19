import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import HelpView from '@/views/Help.vue';

describe('HelpView', () => {
  it('links to the central openHop Repeater documentation', () => {
    const wrapper = mount(HelpView);
    const documentationLink = wrapper.get('a');

    expect(wrapper.text()).toContain('Repeater Documentation');
    expect(wrapper.text()).toContain('Visit Documentation');
    expect(wrapper.text()).not.toContain('Repeater Wiki');
    expect(documentationLink.attributes('href')).toBe(
      'https://docs.openhop.dev/projects/openhop-repeater/',
    );
    expect(documentationLink.attributes('target')).toBe('_blank');
    expect(documentationLink.attributes('rel')).toBe('noopener noreferrer');
  });
});

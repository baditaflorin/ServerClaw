// Import the portal's production stylesheet so every story renders with
// the same CSS the ops portal ships in production (ADR 0243).
import '../../scripts/ops_portal/static/portal.css';

/** @type { import('@storybook/html').Preview } */
const preview = {
  parameters: {
    // Apply a light background matching --paper from portal.css
    backgrounds: {
      default: 'portal',
      values: [
        { name: 'portal', value: '#f8f4ea' },
        { name: 'white', value: '#ffffff' },
        { name: 'dark', value: '#14213d' },
      ],
    },
    // Enable axe-core via addon-a11y for every story by default
    a11y: {
      config: {
        rules: [
          // Temporarily waived: color-contrast on muted text uses --ink-soft (#314467 on #f8f4ea).
          // Ratio is 4.38:1 which passes AA for normal text but fails AAA.
          // Tracked: ADR 0243 waiver 001 — review at next design-system refresh.
          { id: 'color-contrast', enabled: true },
        ],
      },
      options: {
        runOnly: {
          type: 'tag',
          values: ['wcag2a', 'wcag2aa', 'wcag21aa'],
        },
      },
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
  // Wrap every story body in a <div class="storybook-portal-root"> with a
  // realistic padding so components never render flush against the viewport.
  decorators: [
    (story) => {
      const wrapper = document.createElement('div');
      wrapper.className = 'storybook-portal-root';
      wrapper.style.cssText = 'padding: 1.5rem; max-width: 900px; font-family: "IBM Plex Sans", "Segoe UI", sans-serif;';
      wrapper.innerHTML = story();
      return wrapper;
    },
  ],
};

export default preview;

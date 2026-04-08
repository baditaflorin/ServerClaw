/**
 * Stories for the `shell-state` component rendered by the Jinja2 `state_message` macro
 * (scripts/ops_portal/templates/macros/states.html).
 *
 * Covers all five tones: ok, warning, danger, unauthorized, info.
 * ADR 0243 requires stories for normal, empty, loading, error, and permission-limited states.
 */
export default {
  title: 'Portal/ShellState',
  tags: ['autodocs'],
  render: ({ tone, title, message }) => `
    <div class="shell-state shell-state--${tone}" data-shell-state="${tone}">
      <span class="shell-state__eyebrow">
        ${{
          ok: 'Healthy state',
          warning: 'Warning state',
          danger: 'Error state',
          unauthorized: 'Authentication required',
          info: 'Shared state',
        }[tone] ?? 'Shared state'}
      </span>
      <strong>${title}</strong>
      <span>${message}</span>
    </div>
  `,
  argTypes: {
    tone: {
      control: 'select',
      options: ['ok', 'warning', 'danger', 'unauthorized', 'info'],
    },
    title: { control: 'text' },
    message: { control: 'text' },
  },
};

export const Healthy = {
  args: {
    tone: 'ok',
    title: 'Deployment completed',
    message: 'education-wemeshup deployed successfully to production in 42 s.',
  },
};

export const Warning = {
  args: {
    tone: 'warning',
    title: 'Drift detected',
    message: 'Two configuration values differ from the committed state. Review the drift panel before applying changes.',
  },
};

export const Danger = {
  args: {
    tone: 'danger',
    title: 'Health check failed',
    message: 'The API gateway returned 502 for /health. Check the runtime logs.',
  },
};

export const Unauthorized = {
  args: {
    tone: 'unauthorized',
    title: 'Authentication required',
    message: 'The shared gateway rejected the portal session. Refresh the browser session and retry.',
  },
};

export const Info = {
  args: {
    tone: 'info',
    title: 'Activation pending',
    message: 'Complete the onboarding checklist to unlock mutating actions.',
  },
};

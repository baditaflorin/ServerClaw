/**
 * Stories for the action-result component
 * (scripts/ops_portal/templates/partials/action_result.html).
 *
 * Rendered after deploy, health-check, rotate-secret, and runbook actions.
 * Covers: ok (queued), danger (failed), warn (blocked), and link variant.
 */

function actionResult({ title, tone, detail, jobId, linkUrl, linkLabel, timestamp }) {
  const toneMap = {
    ok: 'ok',
    warn: 'warning',
    warning: 'warning',
    danger: 'danger',
    info: 'info',
  };
  const resolvedTone = toneMap[tone] ?? 'info';
  const eyebrow = {
    ok: 'Healthy state',
    warning: 'Warning state',
    danger: 'Error state',
  }[resolvedTone] ?? 'Shared state';

  return `
    <div class="shell-state shell-state--${resolvedTone}" data-shell-state="${resolvedTone}">
      <span class="shell-state__eyebrow">${eyebrow}</span>
      <strong>${title}</strong>
      <span>${detail}</span>
    </div>
    ${jobId ? `<p class="muted action-result-meta">Job ${jobId}</p>` : ''}
    ${linkUrl ? `<p class="action-result-meta"><a href="${linkUrl}">${linkLabel || 'Open details'}</a></p>` : ''}
    <p class="muted action-result-meta">${timestamp}</p>
  `;
}

export default {
  title: 'Portal/ActionResult',
  tags: ['autodocs'],
  render: (args) => actionResult(args),
  argTypes: {
    title: { control: 'text' },
    tone: { control: 'select', options: ['ok', 'warn', 'danger', 'info'] },
    detail: { control: 'text' },
    jobId: { control: 'text' },
    linkUrl: { control: 'text' },
    linkLabel: { control: 'text' },
    timestamp: { control: 'text' },
  },
};

const now = new Date().toISOString();

export const Queued = {
  args: {
    title: 'Deploy: education-wemeshup',
    tone: 'ok',
    detail: 'Deployment queued via Coolify. The build pipeline is starting.',
    jobId: 'job-0041',
    linkUrl: '',
    linkLabel: '',
    timestamp: now,
  },
};

export const Failed = {
  args: {
    title: 'Deploy: my-new-app',
    tone: 'danger',
    detail: 'Docker Hub rate limit reached (429). Retry in 6 hours or configure a registry mirror.',
    jobId: '',
    linkUrl: '',
    linkLabel: '',
    timestamp: now,
  },
};

export const Blocked = {
  args: {
    title: 'Restart: api-gateway',
    tone: 'warn',
    detail: 'Complete the activation checklist or explicitly reveal advanced tools for this session before launching mutating service actions.',
    jobId: '',
    linkUrl: '',
    linkLabel: '',
    timestamp: now,
  },
};

export const WithTaskLink = {
  args: {
    title: 'Runbook: validate-gate',
    tone: 'ok',
    detail: 'Gate validation completed. 3 items passed, 0 items failed.',
    jobId: '',
    linkUrl: '/tasks/runbooks/run-0092',
    linkLabel: 'Review task summary',
    timestamp: now,
  },
};

export const HealthOk = {
  args: {
    title: 'Health check: grafana',
    tone: 'ok',
    detail: 'Grafana responded 200 OK in 48 ms.',
    jobId: '',
    linkUrl: '',
    linkLabel: '',
    timestamp: now,
  },
};

export const HealthFailed = {
  args: {
    title: 'Health check: outline',
    tone: 'danger',
    detail: 'Outline returned 502 Bad Gateway. Check the container logs.',
    jobId: '',
    linkUrl: '',
    linkLabel: '',
    timestamp: now,
  },
};

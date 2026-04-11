/**
 * Stories for the service-card panel used in the deployment console and
 * repo-intake catalog section.
 *
 * Covers: healthy, degraded, unknown, and loading states.
 */

function serviceCard({ name, category, tone, statusLabel, url, meta, actions }) {
  const toneClass = tone ? ` service-card--${tone}` : '';
  const metaRows = (meta || []).map(({ label, value }) => `
    <div>
      <dt>${label}</dt>
      <dd>${value}</dd>
    </div>
  `).join('');
  const actionButtons = (actions || []).map(({ label, primary }) => `
    <button class="action-button${primary ? ' action-button--primary' : ''}" type="button">${label}</button>
  `).join('');

  return `
    <article class="panel service-card${toneClass}">
      <div class="service-card-head">
        <strong>${name}</strong>
        <span class="pill">${category}</span>
        ${statusLabel ? `<span class="service-status">${statusLabel}</span>` : ''}
      </div>
      ${url ? `<p class="muted"><a href="${url}" target="_blank" rel="noopener">${url}</a></p>` : ''}
      ${metaRows ? `<dl class="service-meta-list">${metaRows}</dl>` : ''}
      ${actionButtons ? `<div class="service-card-actions">${actionButtons}</div>` : ''}
    </article>
  `;
}

export default {
  title: 'Portal/ServiceCard',
  tags: ['autodocs'],
  render: (args) => serviceCard(args),
  argTypes: {
    name: { control: 'text' },
    category: { control: 'text' },
    tone: { control: 'select', options: ['', 'ok', 'warn', 'danger'] },
    statusLabel: { control: 'text' },
    url: { control: 'text' },
  },
};

export const Healthy = {
  args: {
    name: 'Grafana',
    category: 'observability',
    tone: 'ok',
    statusLabel: 'healthy',
    url: 'https://grafana.example.com',
    meta: [
      { label: 'Last checked', value: '2 min ago' },
      { label: 'Response', value: '200 OK — 48 ms' },
    ],
    actions: [
      { label: 'Health check', primary: false },
      { label: 'Open', primary: true },
    ],
  },
};

export const Degraded = {
  args: {
    name: 'Outline',
    category: 'knowledge',
    tone: 'warn',
    statusLabel: 'degraded',
    url: 'https://outline.example.com',
    meta: [
      { label: 'Last checked', value: '5 min ago' },
      { label: 'Response', value: '504 Gateway Timeout' },
    ],
    actions: [
      { label: 'Health check', primary: false },
      { label: 'View logs', primary: false },
    ],
  },
};

export const Failed = {
  args: {
    name: 'Plane',
    category: 'planning',
    tone: 'danger',
    statusLabel: 'unreachable',
    url: 'https://plane.example.com',
    meta: [
      { label: 'Last checked', value: '1 min ago' },
      { label: 'Error', value: 'Connection refused' },
    ],
    actions: [
      { label: 'Health check', primary: false },
      { label: 'Restart', primary: true },
    ],
  },
};

export const Unknown = {
  args: {
    name: 'JupyterHub',
    category: 'data',
    tone: '',
    statusLabel: '',
    url: 'https://jupyter.example.com',
    meta: [],
    actions: [
      { label: 'Health check', primary: true },
    ],
  },
};

export const DeployProfile = {
  name: 'Catalog Deploy Profile',
  render: () => `
    <article class="panel service-card">
      <div class="service-card-head">
        <strong>education-wemeshup</strong>
        <span class="pill">production</span>
      </div>
      <p class="muted">Pull the latest committed Docker Compose deployment from upstream main into the governed production Coolify lane.</p>
      <dl class="service-meta-list">
        <div><dt>Repo</dt><dd>git@github.com:baditaflorin/education_wemeshup.git</dd></div>
        <div><dt>Branch</dt><dd>main</dd></div>
        <div><dt>Build pack</dt><dd>dockercompose</dd></div>
        <div><dt>LLM assistance</dt><dd>prohibited</dd></div>
        <div><dt>Domain</dt><dd><a href="https://education-wemeshup.apps.example.com" target="_blank" rel="noopener">education-wemeshup.apps.example.com</a></dd></div>
      </dl>
      <div class="service-card-actions">
        <button class="action-button action-button--primary" type="button">Deploy education-wemeshup</button>
      </div>
    </article>
  `,
};

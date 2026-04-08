/**
 * Stories for the launcher-entry card used in the Application Launcher panel
 * (scripts/ops_portal/templates/partials/launcher.html).
 *
 * Covers: normal, favorite (active star), locked, and compact-grid layouts.
 */

function entryCard({ name, description, summary, badges, primaryBadge, isFavorite, locked }) {
  const favClass = isFavorite ? ' active' : '';
  const favIcon = isFavorite ? '★' : '☆';
  const favLabel = isFavorite ? `Remove ${name} from favorites` : `Add ${name} to favorites`;

  if (locked) {
    return `
      <article class="launcher-entry launcher-entry--locked">
        <div class="launcher-entry-copy">
          <strong class="launcher-entry-link launcher-entry-link--disabled">${name}</strong>
          <p class="muted">${description}</p>
          <div class="launcher-badges">
            <span class="launcher-badge highlighted">${primaryBadge}</span>
            ${badges.map(b => `<span class="launcher-badge">${b}</span>`).join('')}
          </div>
          <p class="muted">Complete the activation checklist or reveal advanced tools for this session to open this destination.</p>
        </div>
      </article>
    `;
  }

  return `
    <article class="launcher-entry">
      <div class="launcher-entry-copy">
        <a class="launcher-entry-link" href="#">${name}</a>
        <p class="muted">${description}</p>
        ${summary ? `<p class="launcher-summary">${summary}</p>` : ''}
        <div class="launcher-badges">
          <span class="launcher-badge highlighted">${primaryBadge}</span>
          ${badges.map(b => `<span class="launcher-badge">${b}</span>`).join('')}
        </div>
      </div>
      <button class="favorite-toggle${favClass}" type="button" aria-label="${favLabel}">
        ${favIcon}
      </button>
    </article>
  `;
}

export default {
  title: 'Portal/LauncherEntry',
  tags: ['autodocs'],
  render: (args) => entryCard(args),
  argTypes: {
    name: { control: 'text' },
    description: { control: 'text' },
    summary: { control: 'text' },
    primaryBadge: { control: 'text' },
    badges: { control: 'object' },
    isFavorite: { control: 'boolean' },
    locked: { control: 'boolean' },
  },
};

export const Default = {
  args: {
    name: 'Grafana',
    description: 'Metrics dashboards, log exploration, and alert management.',
    summary: 'Last checked: 2 min ago',
    primaryBadge: 'Observe',
    badges: ['product', 'observability'],
    isFavorite: false,
    locked: false,
  },
};

export const Favorite = {
  args: {
    name: 'Ops Portal',
    description: 'Governed actions, runbooks, deployments, and live drift visibility.',
    summary: '',
    primaryBadge: 'Start',
    badges: ['task', 'change', 'recover'],
    isFavorite: true,
    locked: false,
  },
};

export const Locked = {
  args: {
    name: 'Keycloak Admin',
    description: 'Identity provider — manage users, groups, and OIDC clients.',
    summary: '',
    primaryBadge: 'Recover',
    badges: ['admin', 'security'],
    isFavorite: false,
    locked: true,
  },
};

export const Grid = {
  render: () => `
    <div class="launcher-entry-grid">
      ${entryCard({ name: 'Grafana', description: 'Metrics and logs.', summary: '', primaryBadge: 'Observe', badges: ['product'], isFavorite: false, locked: false })}
      ${entryCard({ name: 'Gitea', description: 'Source code hosting.', summary: '', primaryBadge: 'Change', badges: ['product'], isFavorite: true, locked: false })}
      ${entryCard({ name: 'Keycloak', description: 'Identity provider.', summary: '', primaryBadge: 'Recover', badges: ['security'], isFavorite: false, locked: true })}
      ${entryCard({ name: 'Outline', description: 'Living wiki.', summary: '', primaryBadge: 'Learn', badges: ['reference'], isFavorite: false, locked: false })}
    </div>
  `,
};

export const CompactGrid = {
  render: () => `
    <div class="launcher-entry-grid compact">
      ${['Grafana', 'Gitea', 'Plane', 'Outline', 'Windmill'].map(name =>
        `<article class="launcher-entry">
          <div class="launcher-entry-copy">
            <a class="launcher-entry-link" href="#">${name}</a>
          </div>
          <button class="favorite-toggle" type="button" aria-label="Add ${name} to favorites">☆</button>
        </article>`
      ).join('')}
    </div>
  `,
};

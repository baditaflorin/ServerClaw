/**
 * Stories for the portal's shared navigation shell: masthead, nav links,
 * lane-badge, and the persona chip row.
 *
 * These components appear on every page of the ops portal and are the primary
 * orientation surface for new users (ADR 0307 workbench model).
 */

function laneBadge(lane) {
  const laneMap = {
    start: { label: 'Start', cls: 'lane-start' },
    observe: { label: 'Observe', cls: 'lane-observe' },
    change: { label: 'Change', cls: 'lane-change' },
    learn: { label: 'Learn', cls: 'lane-learn' },
    recover: { label: 'Recover', cls: 'lane-recover' },
  };
  const meta = laneMap[lane] || { label: lane, cls: 'lane-start' };
  return `<span class="lane-badge ${meta.cls}">${meta.label}</span>`;
}

function navLink({ label, href, active, badge }) {
  return `
    <li>
      <a class="portal-nav-link${active ? ' active' : ''}" href="${href || '#'}">
        ${label}
        ${badge ? `<span class="pill">${badge}</span>` : ''}
      </a>
    </li>
  `;
}

export default {
  title: 'Portal/Navigation',
  tags: ['autodocs'],
};

export const Masthead = {
  render: () => `
    <header class="portal-masthead" role="banner">
      <div class="portal-masthead__brand">
        <span class="portal-masthead__wordmark">LV3 Ops Portal</span>
        <span class="pill">v0.178.49</span>
      </div>
      <nav class="portal-masthead__actions" aria-label="Portal actions">
        <button class="icon-button" type="button" aria-label="Toggle launcher">⊞</button>
        <button class="icon-button" type="button" aria-label="Toggle help">?</button>
      </nav>
    </header>
  `,
};

export const NavBar = {
  render: () => `
    <nav class="portal-nav" aria-label="Main navigation">
      <ul class="portal-nav__list">
        ${navLink({ label: 'Overview', href: '#overview', active: true })}
        ${navLink({ label: 'Repo Deploy', href: '#repo-intake', active: false })}
        ${navLink({ label: 'Agents', href: '#agents', active: false })}
        ${navLink({ label: 'Runtime Assurance', href: '#runtime-assurance', active: false })}
        ${navLink({ label: 'Drift', href: '#drift', active: false, badge: '3' })}
        ${navLink({ label: 'Search', href: '#search', active: false })}
        ${navLink({ label: 'Runbooks', href: '#runbooks', active: false })}
        ${navLink({ label: 'Changelog', href: '#changelog', active: false })}
      </ul>
    </nav>
  `,
};

export const LaneBadges = {
  render: () => `
    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;">
      <p class="muted" style="margin: 0; font-size: 0.875rem;">Workbench lanes:</p>
      ${['start', 'observe', 'change', 'learn', 'recover'].map(laneBadge).join('')}
    </div>
    <p class="muted" style="margin-top: 0.75rem; font-size: 0.8rem;">
      Lane badges contextualise every page — they answer "what kind of job does this surface support?"
    </p>
  `,
};

export const PersonaChips = {
  render: () => `
    <div>
      <p class="muted launcher-persona-copy">
        Showing destinations most useful when your primary job is operating and changing the platform.
      </p>
      <div class="launcher-persona-row">
        ${[
          { id: 'operator', name: 'Operator', active: true },
          { id: 'observer', name: 'Observer', active: false },
          { id: 'planner', name: 'Planner', active: false },
          { id: 'administrator', name: 'Administrator', active: false },
        ].map(p => `
          <button class="persona-chip${p.active ? ' active' : ''}" type="button">${p.name}</button>
        `).join('')}
      </div>
    </div>
  `,
};

export const Pill = {
  render: () => `
    <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
      <span class="pill">production</span>
      <span class="pill">staging</span>
      <span class="pill">42</span>
      <span class="pill">Implemented</span>
      <span class="pill">Partial</span>
    </div>
  `,
};

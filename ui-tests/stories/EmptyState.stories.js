/**
 * Stories for the `shell-empty-state` component rendered by the `empty_state` macro.
 * Used throughout the portal when lists have no items (no tasks, no runbooks, etc.).
 * ADR 0243: every component needs an "empty" state story.
 */
export default {
  title: 'Portal/EmptyState',
  tags: ['autodocs'],
  render: ({ title, message }) => `
    <section class="panel shell-empty-state">
      <div class="shell-empty-state__content">
        <span class="shell-empty-state__eyebrow">Empty state</span>
        <h3>${title}</h3>
        <p class="muted">${message}</p>
      </div>
    </section>
  `,
  argTypes: {
    title: { control: 'text' },
    message: { control: 'text' },
  },
};

export const NoTasks = {
  args: {
    title: 'No resumable task needs review',
    message: 'When a runbook pauses for confirmation or escalation, it will appear here with the saved resume summary.',
  },
};

export const NoRunbooks = {
  args: {
    title: 'No runbooks matched',
    message: 'Adjust the search query or switch persona to reveal runbooks for your role.',
  },
};

export const NoDriftReports = {
  args: {
    title: 'No drift detected',
    message: 'All observed platform configuration matches the committed state.',
  },
};

export const NoSearchResults = {
  args: {
    title: 'No results',
    message: 'Try a broader query or switch the collection to search across the full platform corpus.',
  },
};

export const NoAgents = {
  args: {
    title: 'No active agent sessions',
    message: 'Agents will appear here when they register a workstream or open a coordination task.',
  },
};

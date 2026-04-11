/**
 * Stories for the repo-intake form and result components
 * (scripts/ops_portal/templates/partials/repo_intake.html, ADR 0224).
 *
 * Covers: empty form, validation error, in-progress, success, and the
 * catalog-profiles-only view.
 */

const FORM_HTML = `
  <form class="intake-form" id="intake-form-story">
    <div class="form-row form-row--wide">
      <label class="form-label" for="story-repo">Repository URL <span class="required">*</span></label>
      <input id="story-repo" name="repo" type="text"
        placeholder="git@github.com:org/repo.git or https://github.com/org/repo"
        class="form-input">
      <p class="form-hint">SSH or HTTPS URL. Private repos require <code>private-deploy-key</code> source.</p>
    </div>
    <div class="form-row-group">
      <div class="form-row">
        <label class="form-label" for="story-branch">Branch</label>
        <input id="story-branch" name="branch" type="text" value="main" class="form-input">
      </div>
      <div class="form-row">
        <label class="form-label" for="story-app-name">Application Name <span class="required">*</span></label>
        <input id="story-app-name" name="app_name" type="text" placeholder="my-app" class="form-input">
      </div>
    </div>
    <div class="form-row-group">
      <div class="form-row">
        <label class="form-label" for="story-project">Coolify Project</label>
        <input id="story-project" name="project" type="text" value="LV3 Apps" class="form-input">
      </div>
      <div class="form-row">
        <label class="form-label" for="story-environment">Environment</label>
        <select id="story-environment" name="environment" class="form-select">
          <option value="production">production</option>
          <option value="staging">staging</option>
          <option value="preview">preview</option>
        </select>
      </div>
    </div>
    <div class="form-row-group">
      <div class="form-row">
        <label class="form-label" for="story-build-pack">Build Pack</label>
        <select id="story-build-pack" name="build_pack" class="form-select">
          <option value="dockercompose">dockercompose</option>
          <option value="dockerfile">dockerfile</option>
          <option value="nixpacks">nixpacks</option>
          <option value="static">static</option>
        </select>
      </div>
      <div class="form-row">
        <label class="form-label" for="story-source">Repository Source</label>
        <select id="story-source" name="source" class="form-select">
          <option value="auto">auto</option>
          <option value="public">public</option>
          <option value="private-deploy-key">private-deploy-key</option>
        </select>
      </div>
    </div>
    <div class="form-row-group">
      <div class="form-row">
        <label class="form-label" for="story-domain">Public Domain (optional)</label>
        <input id="story-domain" name="domain" type="text" placeholder="my-app.apps.example.com" class="form-input">
      </div>
      <div class="form-row">
        <label class="form-label" for="story-ports">Exposed Ports</label>
        <input id="story-ports" name="ports" type="text" value="80" class="form-input">
      </div>
    </div>
    <div class="form-actions">
      <button class="action-button action-button--primary" type="submit">Submit Intake Request</button>
    </div>
  </form>
`;

export default {
  title: 'Portal/RepoIntake',
  tags: ['autodocs'],
};

export const EmptyForm = {
  name: 'Empty form',
  render: () => `
    <div id="repo-intake-panel">
      <div class="section-head">
        <div>
          <p class="section-kicker">Change lane — Repo Intake</p>
          <h2>Self-Service Repository Deployment</h2>
          <p class="muted">Deploy a governed repository through the Coolify lane.</p>
        </div>
      </div>
      <section class="intake-custom-section">
        <div class="section-head section-head--compact">
          <div>
            <p class="section-kicker">Custom Intake</p>
            <h3>Deploy from repository URL</h3>
          </div>
        </div>
        ${FORM_HTML}
      </section>
      <div id="repo-intake-result" class="intake-result-area"></div>
    </div>
  `,
};

export const ValidationError = {
  name: 'Validation error state',
  render: () => `
    <div id="repo-intake-panel">
      <div class="shell-state shell-state--danger" data-shell-state="danger">
        <span class="shell-state__eyebrow">Error state</span>
        <strong>Intake validation failed</strong>
        <span>Repository URL is required. Application name is required.</span>
      </div>
      <section class="intake-custom-section">
        <div class="section-head section-head--compact">
          <div>
            <p class="section-kicker">Custom Intake</p>
            <h3>Deploy from repository URL</h3>
          </div>
        </div>
        ${FORM_HTML}
      </section>
    </div>
  `,
};

export const WithCatalogProfiles = {
  name: 'With catalog profiles',
  render: () => `
    <div id="repo-intake-panel">
      <div class="section-head">
        <div>
          <p class="section-kicker">Change lane — Repo Intake</p>
          <h2>Self-Service Repository Deployment</h2>
        </div>
      </div>
      <section class="intake-catalog-section">
        <div class="section-head section-head--compact">
          <div>
            <p class="section-kicker">Catalog Profiles</p>
            <h3>Governed deployment profiles</h3>
            <p class="muted">These profiles are declared in the repo-deploy-catalog and validated before every deploy.</p>
          </div>
          <span class="pill">1</span>
        </div>
        <div class="service-card-grid">
          <article class="panel service-card">
            <div class="service-card-head">
              <strong>education-wemeshup</strong>
              <span class="pill">production</span>
            </div>
            <p class="muted">Pull the latest committed Docker Compose deployment from upstream main.</p>
            <dl class="service-meta-list">
              <div><dt>Repo</dt><dd class="truncate">git@github.com:baditaflorin/education_wemeshup.git</dd></div>
              <div><dt>Branch</dt><dd>main</dd></div>
              <div><dt>Build pack</dt><dd>dockercompose</dd></div>
              <div><dt>LLM assistance</dt><dd>prohibited</dd></div>
              <div><dt>Domain</dt><dd><a href="#">education-wemeshup.apps.example.com</a></dd></div>
            </dl>
            <div class="service-card-actions">
              <button class="action-button action-button--primary" type="button">Deploy education-wemeshup</button>
            </div>
          </article>
        </div>
      </section>
    </div>
  `,
};

export const DeployQueued = {
  name: 'Post-submit — queued',
  render: () => `
    <div class="shell-state shell-state--ok" data-shell-state="ok">
      <span class="shell-state__eyebrow">Healthy state</span>
      <strong>Repo deploy: education-wemeshup</strong>
      <span>Profile 'education-wemeshup-production' deploy queued via Coolify.</span>
    </div>
    <p class="muted action-result-meta">${new Date().toISOString()}</p>
  `,
};

export const DeployFailed = {
  name: 'Post-submit — failed',
  render: () => `
    <div class="shell-state shell-state--danger" data-shell-state="danger">
      <span class="shell-state__eyebrow">Error state</span>
      <strong>Repo deploy: my-new-app</strong>
      <span>Deploy command exited non-zero. Check that the repo URL is accessible and the deploy key is installed.</span>
    </div>
    <p class="muted action-result-meta">${new Date().toISOString()}</p>
  `,
};

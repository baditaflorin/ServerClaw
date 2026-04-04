(() => {
  const instances = new Map();
  const body = document.body;
  const navToggle = document.querySelector("[data-portal-nav-toggle]");
  const sidebar = document.querySelector("[data-portal-sidebar]");
  const launcherToggle = document.getElementById("launcher-toggle");
  const launcherShell = document.getElementById("launcher-shell");
  const contextualHelpToggle = document.getElementById("contextual-help-toggle");
  const contextualHelpDrawer = document.getElementById("contextual-help-drawer");
  const contextualHelpDismiss = document.querySelectorAll("[data-contextual-help-dismiss]");

  function setSidebarOpen(isOpen) {
    body.classList.toggle("portal-sidebar-open", isOpen);
    if (navToggle) {
      navToggle.setAttribute("aria-expanded", String(isOpen));
    }
  }

  function setLauncherOpen(isOpen) {
    if (!launcherShell || !launcherToggle) {
      return;
    }
    launcherShell.hidden = !isOpen;
    launcherToggle.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) {
      const searchInput = launcherShell.querySelector('input[name="query"]');
      if (searchInput instanceof HTMLElement) {
        searchInput.focus();
      }
    }
  }

  function setContextualHelpOpen(isOpen) {
    if (!contextualHelpToggle || !contextualHelpDrawer) {
      return;
    }
    contextualHelpDrawer.hidden = !isOpen;
    contextualHelpToggle.setAttribute("aria-expanded", String(isOpen));
    body.classList.toggle("contextual-help-open", isOpen);
    contextualHelpDismiss.forEach((element) => {
      if (element instanceof HTMLElement) {
        element.hidden = !isOpen;
      }
    });
  }

  function storageAvailable() {
    try {
      const key = "__lv3_portal_storage_test__";
      window.localStorage.setItem(key, "ok");
      window.localStorage.removeItem(key);
      return true;
    } catch (_error) {
      return false;
    }
  }

  const hasLocalStorage = storageAvailable();

  function draftStorageKey(runbookId) {
    return `lv3.runbookDraft.${runbookId}`;
  }

  function setDraftStatus(runbookId, message) {
    const status = document.querySelector(`[data-draft-status-for="${runbookId}"]`);
    if (status) {
      status.textContent = message;
    }
  }

  function bindRunbookDrafts(root = document) {
    root.querySelectorAll("form[data-runbook-form]").forEach((form) => {
      if (!(form instanceof HTMLFormElement) || form.dataset.draftBound === "true") {
        return;
      }

      const runbookId = form.dataset.runbookId;
      const input = form.querySelector("[data-runbook-draft-input]");
      const clearButton = form.querySelector("[data-clear-runbook-draft]");
      if (!runbookId || !(input instanceof HTMLTextAreaElement)) {
        return;
      }

      form.dataset.draftBound = "true";
      if (hasLocalStorage) {
        const savedDraft = window.localStorage.getItem(draftStorageKey(runbookId));
        if (savedDraft && (!input.value.trim() || input.value.trim() === "{}")) {
          input.value = savedDraft;
          setDraftStatus(runbookId, "Draft restored from this browser.");
        }
      } else {
        setDraftStatus(runbookId, "Browser-local drafts are unavailable in this session.");
      }

      input.addEventListener("input", () => {
        if (!hasLocalStorage) {
          return;
        }
        const value = input.value.trim();
        if (!value || value === "{}") {
          window.localStorage.removeItem(draftStorageKey(runbookId));
          setDraftStatus(runbookId, "Drafts stay in this browser until you clear them.");
          return;
        }
        window.localStorage.setItem(draftStorageKey(runbookId), input.value);
        setDraftStatus(runbookId, "Draft saved in this browser.");
      });

      if (clearButton instanceof HTMLButtonElement) {
        clearButton.addEventListener("click", () => {
          input.value = "{}";
          if (hasLocalStorage) {
            window.localStorage.removeItem(draftStorageKey(runbookId));
          }
          setDraftStatus(runbookId, "Draft cleared for this runbook.");
        });
      }
    });
  }

  if (navToggle && sidebar) {
    navToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      setSidebarOpen(!body.classList.contains("portal-sidebar-open"));
    });

    sidebar.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  }

  if (launcherToggle && launcherShell) {
    launcherToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = launcherToggle.getAttribute("aria-expanded") === "true";
      setLauncherOpen(!isOpen);
    });

    launcherShell.addEventListener("click", (event) => {
      event.stopPropagation();
    });
  }

  if (contextualHelpToggle && contextualHelpDrawer) {
    contextualHelpToggle.addEventListener("click", (event) => {
      event.stopPropagation();
      const isOpen = contextualHelpToggle.getAttribute("aria-expanded") === "true";
      setContextualHelpOpen(!isOpen);
    });

    contextualHelpDrawer.addEventListener("click", (event) => {
      event.stopPropagation();
    });

    contextualHelpDismiss.forEach((element) => {
      element.addEventListener("click", () => {
        setContextualHelpOpen(false);
      });
    });
  }

  function initCharts(root = document) {
    if (typeof window.echarts === "undefined") {
      return;
    }

    root.querySelectorAll("[data-echart-target]").forEach((element) => {
      const sourceId = element.dataset.echartTarget;
      if (!sourceId) {
        return;
      }
      const source = document.getElementById(sourceId);
      if (!source) {
        return;
      }

      try {
        const option = JSON.parse(source.textContent || "{}");
        const existing = window.echarts.getInstanceByDom(element);
        if (existing) {
          existing.dispose();
        }
        const chart = window.echarts.init(element, null, { renderer: "canvas" });
        chart.setOption(option, true);
        instances.set(sourceId, chart);
      } catch (error) {
        console.error(`Failed to initialize chart ${sourceId}`, error);
      }
    });
  }

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Node)) {
      return;
    }

    if (
      launcherShell &&
      launcherToggle &&
      !launcherShell.hidden &&
      !launcherShell.contains(event.target) &&
      !launcherToggle.contains(event.target)
    ) {
      setLauncherOpen(false);
    }

    if (
      contextualHelpDrawer &&
      contextualHelpToggle &&
      !contextualHelpDrawer.hidden &&
      !contextualHelpDrawer.contains(event.target) &&
      !contextualHelpToggle.contains(event.target)
    ) {
      setContextualHelpOpen(false);
    }

    if (
      window.innerWidth <= 960 &&
      body.classList.contains("portal-sidebar-open") &&
      sidebar &&
      navToggle &&
      !sidebar.contains(event.target) &&
      !navToggle.contains(event.target)
    ) {
      setSidebarOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    if (launcherShell && !launcherShell.hidden) {
      setLauncherOpen(false);
      launcherToggle?.focus();
    }
    if (contextualHelpDrawer && !contextualHelpDrawer.hidden) {
      setContextualHelpOpen(false);
      contextualHelpToggle?.focus();
    }
    if (body.classList.contains("portal-sidebar-open")) {
      setSidebarOpen(false);
      navToggle?.focus();
    }
  });

  function resizeCharts() {
    instances.forEach((chart) => chart.resize());
  }

  function connectDeploymentStream() {
    const consoleLog = document.getElementById("deployment-console-log");
    if (!consoleLog || consoleLog.dataset.streamAttached === "true") {
      return;
    }
    consoleLog.dataset.streamAttached = "true";

    const stream = new EventSource("/events/deployments");

    function appendConsoleLine(payload) {
      const timestamp = payload.ts || new Date().toISOString();
      const message = payload.message || JSON.stringify(payload);
      if (consoleLog.textContent.includes("Connecting to deployment stream")) {
        consoleLog.textContent = "";
      }
      consoleLog.textContent += `[${timestamp}] ${message}\n`;
      consoleLog.scrollTop = consoleLog.scrollHeight;
    }

    stream.addEventListener("heartbeat", () => {});
    stream.addEventListener("log", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("deploy", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("secret", (event) => appendConsoleLine(JSON.parse(event.data)));
    stream.addEventListener("runbook", (event) => appendConsoleLine(JSON.parse(event.data)));
  }

  document.addEventListener("DOMContentLoaded", () => {
    initCharts(document);
    bindRunbookDrafts(document);
    connectDeploymentStream();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.target instanceof HTMLElement) {
      initCharts(event.target);
      bindRunbookDrafts(event.target);
    } else {
      initCharts(document);
      bindRunbookDrafts(document);
    }
    resizeCharts();
  });

  window.addEventListener("resize", () => {
    resizeCharts();
    if (window.innerWidth > 960) {
      setSidebarOpen(false);
    }
  });
})();

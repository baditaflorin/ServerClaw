(() => {
  const SEARCH_TOGGLE_ID = "__search";
  const SEARCH_CONTAINER_ID = "pagefind-search";
  let initialized = false;

  function searchToggle() {
    return document.getElementById(SEARCH_TOGGLE_ID);
  }

  function searchContainer() {
    return document.getElementById(SEARCH_CONTAINER_ID);
  }

  function searchInput() {
    return document.querySelector(`#${SEARCH_CONTAINER_ID} .pagefind-ui__search-input`);
  }

  function isEditableTarget(target) {
    if (!(target instanceof HTMLElement)) {
      return false;
    }
    if (target.isContentEditable) {
      return true;
    }
    return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
  }

  function focusSearchInput() {
    const input = searchInput();
    if (!input) {
      return;
    }
    input.focus();
    input.select();
  }

  function initializeSearch() {
    if (initialized || typeof window.PagefindUI !== "function") {
      return;
    }

    const container = searchContainer();
    if (!container) {
      return;
    }

    const bundlePath = container.dataset.pagefindBase;
    new window.PagefindUI({
      element: `#${SEARCH_CONTAINER_ID}`,
      bundlePath,
    });
    initialized = true;

    window.setTimeout(() => {
      const input = searchInput();
      if (!input) {
        return;
      }
      if (container.dataset.pagefindPlaceholder) {
        input.placeholder = container.dataset.pagefindPlaceholder;
      }
    }, 0);
  }

  function setSearchOpen(open) {
    const toggle = searchToggle();
    if (!toggle) {
      return;
    }
    toggle.checked = open;
    if (!open) {
      return;
    }
    initializeSearch();
    window.requestAnimationFrame(() => {
      window.setTimeout(focusSearchInput, 60);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = searchToggle();
    if (toggle) {
      toggle.addEventListener("change", () => {
        if (toggle.checked) {
          initializeSearch();
          window.setTimeout(focusSearchInput, 60);
        }
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && toggle?.checked) {
        toggle.checked = false;
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
        return;
      }

      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && !isEditableTarget(event.target)) {
        event.preventDefault();
        setSearchOpen(true);
      }
    });
  });
})();

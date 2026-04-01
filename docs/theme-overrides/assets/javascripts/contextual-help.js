(() => {
  function setOpen(isOpen) {
    const toggle = document.querySelector("[data-contextual-help-toggle]");
    const drawer = document.getElementById("lv3-contextual-help-drawer");
    const dismissers = document.querySelectorAll("[data-contextual-help-dismiss]");
    if (!(toggle instanceof HTMLElement) || !(drawer instanceof HTMLElement)) {
      return;
    }
    toggle.setAttribute("aria-expanded", String(isOpen));
    drawer.hidden = !isOpen;
    document.documentElement.classList.toggle("lv3-contextual-help-open", isOpen);
    dismissers.forEach((element) => {
      if (element instanceof HTMLElement) {
        element.hidden = !isOpen;
      }
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
      return;
    }
    if (target.closest("[data-contextual-help-toggle]")) {
      const toggle = document.querySelector("[data-contextual-help-toggle]");
      if (toggle instanceof HTMLElement) {
        const isOpen = toggle.getAttribute("aria-expanded") === "true";
        setOpen(!isOpen);
      }
      return;
    }
    if (target.closest("[data-contextual-help-dismiss]")) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    const drawer = document.getElementById("lv3-contextual-help-drawer");
    if (drawer instanceof HTMLElement && !drawer.hidden) {
      setOpen(false);
      const toggle = document.querySelector("[data-contextual-help-toggle]");
      if (toggle instanceof HTMLElement) {
        toggle.focus();
      }
    }
  });
})();

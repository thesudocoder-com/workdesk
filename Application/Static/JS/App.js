(() => {
  const sidebar = document.querySelector("#app-sidebar");
  const openButtons = document.querySelectorAll("[data-sidebar-open]");
  const collapseButton = document.querySelector("[data-sidebar-collapse]");
  const desktopSidebar = window.matchMedia("(min-width: 901px)");
  const modalRoot = document.querySelector("#modal-root");
  let modalOpener = null;

  const hasOpenModal = () => Boolean(modalRoot?.querySelector(".modal-card"));
  const syncBodyLock = () => {
    const drawerOpen = Boolean(sidebar?.classList.contains("is-open"));
    const modalOpen = hasOpenModal();
    const locked = drawerOpen || modalOpen;
    document.body.classList.toggle("modal-open", modalOpen);
    document.body.style.overflow = locked ? "hidden" : "";
    document.body.style.touchAction = drawerOpen ? "none" : "";
  };

  const closeModal = ({ restoreFocus = true } = {}) => {
    if (!modalRoot?.hasChildNodes()) return;
    modalRoot.replaceChildren();
    syncBodyLock();
    if (restoreFocus && modalOpener?.isConnected) modalOpener.focus();
    modalOpener = null;
  };

  // Sidebar collapse state for desktop
  let collapsePreference = (() => {
    try { return localStorage.getItem("workdesk.sidebar.collapsed") === "true"; }
    catch { return false; }
  })();

  const setCollapsed = (collapsed) => {
    const active = desktopSidebar.matches && collapsed;
    document.body.classList.toggle("sidebar-collapsed", active);
    collapseButton?.setAttribute("aria-pressed", String(active));
    collapseButton?.setAttribute("aria-label", active ? "Expand sidebar" : "Collapse sidebar");
    collapseButton?.setAttribute("title", active ? "Expand sidebar" : "Collapse sidebar");
    collapsePreference = collapsed;
    try { localStorage.setItem("workdesk.sidebar.collapsed", String(collapsed)); }
    catch { /* Optional UI storage */ }
  };

  if (desktopSidebar.matches) {
    setCollapsed(collapsePreference);
  }

  collapseButton?.addEventListener("click", () => {
    if (!desktopSidebar.matches) return;
    setCollapsed(!document.body.classList.contains("sidebar-collapsed"));
  });

  const handleBreakpointChange = (e) => {
    closeSidebar();
    if (e.matches) {
      setCollapsed(collapsePreference);
    } else {
      document.body.classList.remove("sidebar-collapsed");
    }
  };
  if (desktopSidebar.addEventListener) desktopSidebar.addEventListener("change", handleBreakpointChange);
  else desktopSidebar.addListener(handleBreakpointChange);

  // Mobile drawer open/close
  const closeSidebar = () => {
    if (!sidebar) return;
    sidebar.classList.remove("is-open");
    openButtons.forEach((button) => button.setAttribute("aria-expanded", "false"));
    document.body.classList.remove("sidebar-open");
    syncBodyLock();
  };

  const openSidebar = () => {
    if (!sidebar) return;
    sidebar.classList.add("is-open");
    openButtons.forEach((button) => button.setAttribute("aria-expanded", "true"));
    document.body.classList.add("sidebar-open");
    syncBodyLock();
  };

  openButtons.forEach((button) => {
    button.addEventListener("click", (e) => {
      e.preventDefault();
      if (sidebar?.classList.contains("is-open")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  });

  document.querySelectorAll("[data-sidebar-close]").forEach((element) => {
    element.addEventListener("click", (e) => {
      e.preventDefault();
      closeSidebar();
    });
  });

  sidebar?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      if (!desktopSidebar.matches) closeSidebar();
    });
  });

  // Mobile Search Toggle
  document.querySelectorAll("[data-search-toggle]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const searchForm = document.querySelector(".global-search");
      if (searchForm) {
        searchForm.classList.toggle("mobile-expanded");
        const input = searchForm.querySelector('input[name="q"]');
        if (searchForm.classList.contains("mobile-expanded") && input) {
          input.focus();
        }
      }
    });
  });

  // Global click management: modals, details, dropdowns, toasts
  document.addEventListener("click", (event) => {
    const modalTrigger = event.target.closest('[hx-target="#modal-root"]');
    if (modalTrigger && !modalTrigger.closest("#modal-root")) modalOpener = modalTrigger;

    // Modal close button or backdrop click
    const close = event.target.closest("[data-modal-close]");
    if (close && modalRoot?.contains(close)) {
      event.preventDefault();
      closeModal();
    }

    // Dismiss search results if clicked outside search popover and search input
    const searchPopover = event.target.closest(".search-results-popover");
    const searchForm = event.target.closest(".global-search");
    const searchToggle = event.target.closest("[data-search-toggle]");
    if (!searchPopover && !searchForm && !searchToggle && modalRoot?.querySelector(".search-results-popover")) {
      modalRoot.replaceChildren();
      document.querySelector(".global-search")?.classList.remove("mobile-expanded");
    }

    // Toast close button
    const toastClose = event.target.closest("[data-toast-close]");
    if (toastClose) {
      const toast = toastClose.closest("[data-toast]");
      if (toast) {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(10px)";
        setTimeout(() => toast.remove(), 200);
      }
    }

    // Auto-close open <details> when clicking outside
    document.querySelectorAll("details[open]").forEach((details) => {
      if (!details.contains(event.target)) {
        details.removeAttribute("open");
      }
    });
  });

  // Password visibility toggle
  document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-password-toggle]");
    if (!toggle) return;
    const inputId = toggle.dataset.passwordToggle;
    const input = document.getElementById(inputId);
    if (!input) return;
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    toggle.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
  });

  // Keyboard navigation shortcuts
  document.addEventListener("keydown", (event) => {
    // ⌘K / Ctrl+K focus search
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      const search = document.querySelector('.global-search input[name="q"]');
      if (search) {
        event.preventDefault();
        const searchForm = document.querySelector(".global-search");
        searchForm?.classList.add("mobile-expanded");
        search.focus();
        search.select();
      }
    }

    // Escape closes search, modal, drawer, open details
    if (event.key === "Escape") {
      closeSidebar();
      closeModal();
      document.querySelector(".global-search")?.classList.remove("mobile-expanded");
      document.querySelectorAll("details[open]").forEach((d) => d.removeAttribute("open"));
    }

    // Keep keyboard focus inside an open dialog.
    if (event.key === "Tab" && hasOpenModal()) {
      const dialog = modalRoot.querySelector('.modal-card[role="dialog"]');
      const focusable = [...dialog.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
        .filter((element) => element.getClientRects().length);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  // HTMX lifecycle hooks
  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if ([400, 409, 422].includes(event.detail.xhr.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target.id === "modal-root") {
      syncBodyLock();
      const summary = event.detail.target.querySelector("[data-form-summary]");
      const firstInput = event.detail.target.querySelector("input:not([type=hidden]), select, textarea");
      const closeButton = event.detail.target.querySelector("[data-modal-close]");
      (summary || firstInput || closeButton)?.focus();
    }
  });

  document.body.addEventListener("htmx:afterRequest", () => {
    document.querySelectorAll(".row-menu[open], .profile-menu[open], .notification-menu[open]").forEach((menu) => {
      menu.removeAttribute("open");
    });
  });

  // Toast auto-dismiss with hover pause
  const initToasts = () => {
    document.querySelectorAll("[data-toast]").forEach((toast) => {
      let timeoutId;
      const startTimer = () => {
        timeoutId = window.setTimeout(() => {
          toast.style.transition = "opacity 0.25s ease, transform 0.25s ease";
          toast.style.opacity = "0";
          toast.style.transform = "translateY(10px)";
          setTimeout(() => toast.remove(), 250);
        }, 5000);
      };
      const clearTimer = () => window.clearTimeout(timeoutId);

      toast.addEventListener("mouseenter", clearTimer);
      toast.addEventListener("mouseleave", startTimer);
      toast.addEventListener("touchstart", clearTimer, { passive: true });
      toast.addEventListener("touchend", startTimer, { passive: true });

      startTimer();
    });
  };

  initToasts();

  // Keep the dashboard clock aligned with the workspace timezone.
  const clock = document.querySelector("[data-workspace-clock]");
  if (clock) {
    const updateClock = () => {
      try {
        clock.textContent = new Intl.DateTimeFormat(undefined, {
          timeZone: clock.dataset.timezone,
          hour: "numeric",
          minute: "2-digit",
        }).format(new Date());
      } catch { /* The server-rendered time remains a safe fallback. */ }
    };
    updateClock();
    window.setInterval(updateClock, 30000);
  }

  // Full-page validation responses should announce the summary immediately.
  document.querySelector("[data-form-summary]")?.focus();
})();

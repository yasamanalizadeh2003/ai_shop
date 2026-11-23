(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  // ---------- Drawers (cart drawer, mobile filter sheet) ----------
  const openDrawer = (name) => {
    const el = $(`[data-drawer="${name}"]`);
    if (!el) return;
    el.classList.remove("hidden");
    document.documentElement.classList.add("overflow-hidden");
  };
  const closeDrawer = (el) => {
    el.classList.add("hidden");
    document.documentElement.classList.remove("overflow-hidden");
  };

  document.addEventListener("click", (e) => {
    const opener = e.target.closest("[data-drawer-open]");
    if (opener) openDrawer(opener.dataset.drawerOpen);

    const closer = e.target.closest("[data-drawer-close]");
    if (closer) {
      const drawer = closer.closest("[data-drawer]");
      // The filter sidebar is a static column on desktop; only close it on mobile.
      if (drawer && getComputedStyle(drawer).position === "fixed") closeDrawer(drawer);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $$("[data-drawer]:not(.hidden)").forEach((d) => {
      if (getComputedStyle(d).position === "fixed") closeDrawer(d);
    });
  });

  // ---------- Search suggestions (from the backend) ----------
  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  $$("[data-search]").forEach((box) => {
    const input = $("[data-search-input]", box);
    const panel = $("[data-search-panel]", box);
    const list = $("[data-search-results]", box);
    if (!input) return;
    let timer = null;
    let controller = null;

    const render = async () => {
      const q = input.value.trim();
      if (q.length < 2) return panel.classList.add("hidden");
      if (controller) controller.abort();
      controller = new AbortController();
      try {
        const res = await fetch(`/search/suggest/?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        const { results } = await res.json();
        list.innerHTML = results.length
          ? results.map((h) => `<li><a href="${escapeHtml(h.url)}" class="flex items-center justify-between gap-2 px-4 py-2.5 hover:bg-slate-50"><span>${escapeHtml(h.title)}</span><span class="text-xs text-slate-400">${escapeHtml(h.price)}</span></a></li>`).join("")
          : `<li class="px-4 py-3 text-slate-500">نتیجه‌ای پیدا نشد؛ عبارت دیگری امتحان کنید.</li>`;
        panel.classList.remove("hidden");
      } catch (err) {
        if (err.name !== "AbortError") panel.classList.add("hidden");
      }
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(render, 200); });
    input.addEventListener("focus", render);
    document.addEventListener("click", (e) => { if (!box.contains(e.target)) panel.classList.add("hidden"); });
  });

  // ---------- Auto-submit filters (selects always; checkboxes only on desktop) ----------
  $$("[data-autosubmit]").forEach((el) => el.addEventListener("change", () => {
    if (el.tagName === "SELECT" || window.matchMedia("(min-width: 1024px)").matches) el.form.requestSubmit();
  }));

  // ---------- Product page: variant picker ----------
  const product = $("[data-product]");
  if (product) {
    const buttons = $$("[data-variant]", product);
    const select = (btn) => {
      buttons.forEach((b) => b.setAttribute("aria-checked", String(b === btn)));
      const d = btn.dataset;
      $$("[data-variant-name]").forEach((el) => (el.textContent = d.vName));
      $$("[data-price]").forEach((el) => (el.textContent = d.vPrice));
      $$("[data-compare]").forEach((el) => { el.textContent = d.vCompare; el.hidden = !d.vCompare; });
      $$("[data-off-badge]").forEach((el) => { el.textContent = `${d.vOff}٪`; el.hidden = !d.vOff; });
      $$("[data-delivery]").forEach((el) => (el.textContent = d.vDelivery));
      $$("[data-warranty]").forEach((el) => (el.textContent = d.vWarranty));
      $$("[data-private-note]").forEach((el) => { el.classList.toggle("hidden", !d.vPrivate); el.classList.toggle("flex", !!d.vPrivate); });
      $$("[data-add-to-cart]").forEach((el) => {
        el.disabled = !d.vStock;
        el.textContent = d.vStock ? (el.closest("aside") ? "افزودن به سبد خرید" : "افزودن به سبد") : "ناموجود";
      });
      const drawerVariant = $("[data-drawer-variant]");
      if (drawerVariant) drawerVariant.textContent = d.vName;
      const drawerTitle = $("[data-drawer-title]");
      const h1 = $("main h1");
      if (drawerTitle && h1) drawerTitle.textContent = h1.textContent;
    };
    buttons.forEach((b) => b.addEventListener("click", () => select(b)));
    const initial = buttons.find((b) => b.getAttribute("aria-checked") === "true") || buttons[0];
    if (initial) select(initial);
  }

  // ---------- Add to cart ----------
  const csrf = () => $('meta[name="csrf-token"]')?.content || "";
  const faDigits = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
  const showToast = (text) => {
    let el = $("[data-toast]");
    if (!el) {
      el = document.createElement("div");
      el.dataset.toast = "";
      el.setAttribute("role", "alert");
      el.className = "fixed inset-x-4 bottom-24 z-[60] mx-auto max-w-sm rounded-xl bg-slate-900 px-4 py-3 text-center text-sm text-white shadow-lg lg:bottom-8";
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.hidden = false;
    clearTimeout(el._t);
    el._t = setTimeout(() => (el.hidden = true), 4000);
  };

  $$("[data-add-to-cart]").forEach((btn) => btn.addEventListener("click", async () => {
    const selected = $('[data-variant][aria-checked="true"]');
    if (!selected || btn.disabled) return;
    btn.disabled = true;
    try {
      const res = await fetch("/cart/add/", {
        method: "POST",
        headers: { "X-CSRFToken": csrf(), Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ variant: selected.dataset.vId, quantity: "1" }),
      });
      const data = await res.json();
      if (!data.ok) return showToast(data.error || "افزودن به سبد ممکن نشد.");
      $$("[data-cart-count]").forEach((el) => { el.textContent = faDigits(data.count); el.hidden = !data.count; });
      openDrawer("cart");
    } catch {
      showToast("اتصال برقرار نشد؛ دوباره تلاش کنید.");
    } finally {
      btn.disabled = !selected.dataset.vStock;
    }
  }));

  // ---------- Tabs ----------
  $$("[data-tabs]").forEach((root) => {
    const tabs = $$("[data-tab]", root);
    tabs.forEach((tab) => tab.addEventListener("click", () => {
      tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      $$("[data-panel]", root).forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== tab.dataset.tab));
    }));
  });

  // ---------- OTP inputs: auto-advance, paste, auto-submit ----------
  const toLatin = (s) => s.replace(/[۰-۹]/g, (d) => "۰۱۲۳۴۵۶۷۸۹".indexOf(d)).replace(/[٠-٩]/g, (d) => "٠١٢٣٤٥٦٧٨٩".indexOf(d));
  $$("[data-otp]").forEach((root) => {
    const inputs = $$("input", root);
    const form = root.closest("form");
    const fill = (digits, start = 0) => {
      digits.split("").forEach((d, k) => { if (inputs[start + k]) inputs[start + k].value = d; });
      const next = inputs.find((el) => !el.value);
      if (next) next.focus();
      else if (form) form.requestSubmit();
    };
    inputs.forEach((input, i) => {
      input.addEventListener("input", () => {
        const digits = toLatin(input.value).replace(/\D/g, "");
        input.value = "";
        if (digits) fill(digits, i);
      });
      input.addEventListener("paste", (e) => {
        e.preventDefault();
        fill(toLatin(e.clipboardData.getData("text")).replace(/\D/g, ""), 0);
      });
      input.addEventListener("keydown", (e) => { if (e.key === "Backspace" && !input.value && inputs[i - 1]) inputs[i - 1].focus(); });
    });
  });

  // ---------- Countdown (OTP resend) ----------
  const fa = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
  $$("[data-countdown]").forEach((el) => {
    let left = parseInt(el.dataset.countdown, 10) || 0;
    const text = $("[data-countdown-text]", el);
    const done = $("[data-countdown-done]", el.parentElement);
    const tick = () => {
      if (left <= 0) {
        el.classList.add("hidden");
        if (done) done.classList.remove("hidden");
        return;
      }
      const m = Math.floor(left / 60), s = left % 60;
      text.textContent = fa(`${m}:${String(s).padStart(2, "0")}`);
      left -= 1;
      setTimeout(tick, 1000);
    };
    tick();
  });
})();

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

  // ---------- Search suggestions (sample data; will call the backend later) ----------
  const SUGGESTIONS = [
    { slug: "اشتراک-chatgpt-plus", title: "اشتراک ChatGPT Plus", keys: ["chatgpt", "چت جی پی تی", "چت‌جی‌پی‌تی", "openai", "gpt"] },
    { slug: "اشتراک-جمینای", title: "اشتراک Gemini Advanced", keys: ["gemini", "جمینای", "جمنای", "هوش مصنوعی گوگل", "google"] },
    { slug: "اشتراک-claude-pro", title: "اشتراک Claude Pro", keys: ["claude", "کلود", "anthropic"] },
    { slug: "اشتراک-midjourney", title: "اشتراک Midjourney", keys: ["midjourney", "میدجرنی", "تولید تصویر"] },
    { slug: "اشتراک-cursor-pro", title: "اشتراک Cursor Pro", keys: ["cursor", "کرسر", "برنامه نویسی"] },
    { slug: "اشتراک-perplexity-pro", title: "اشتراک Perplexity Pro", keys: ["perplexity", "پرپلکسیتی"] },
    { slug: "اشتراک-github-copilot", title: "اشتراک GitHub Copilot", keys: ["copilot", "کوپایلوت", "github"] },
  ];
  const norm = (s) => s.toLowerCase().replace(/\u200c/g, " ").replace(/ي/g, "ی").replace(/ك/g, "ک").trim();

  $$("[data-search]").forEach((box) => {
    const input = $("[data-search-input]", box);
    const panel = $("[data-search-panel]", box);
    const list = $("[data-search-results]", box);
    if (!input) return;

    const render = () => {
      const q = norm(input.value);
      if (!q) return panel.classList.add("hidden");
      const hits = SUGGESTIONS.filter((s) => norm(s.title).includes(q) || s.keys.some((k) => norm(k).includes(q)));
      list.innerHTML = hits.length
        ? hits.map((h) => `<li><a href="/product/${encodeURIComponent(h.slug)}/" class="flex items-center gap-2 px-4 py-2.5 hover:bg-slate-50">🔍 ${h.title}</a></li>`).join("")
        : `<li class="px-4 py-3 text-slate-500">نتیجه‌ای پیدا نشد؛ عبارت دیگری امتحان کنید.</li>`;
      panel.classList.remove("hidden");
    };
    input.addEventListener("input", render);
    input.addEventListener("focus", render);
    document.addEventListener("click", (e) => { if (!box.contains(e.target)) panel.classList.add("hidden"); });
  });

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
    };
    buttons.forEach((b) => b.addEventListener("click", () => select(b)));
    if (buttons[0]) select(buttons[0]);
  }

  $$("[data-add-to-cart]").forEach((btn) => btn.addEventListener("click", () => openDrawer("cart")));

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
